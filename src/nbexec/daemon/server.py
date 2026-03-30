import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from nbexec import protocol as proto
from nbexec.paths import socket_path
from .state import DaemonState

logger = logging.getLogger("nbexec.daemon")


class DaemonServer:
    def __init__(self):
        self.state = DaemonState()
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.shutdown_event = asyncio.Event()

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    request = proto.decode(line)
                except json.JSONDecodeError:
                    writer.write(proto.encode(proto.make_error("?", "Invalid JSON")))
                    await writer.drain()
                    continue

                req_id = request.get("id", "?")
                method = request.get("method", "")
                params = request.get("params", {})

                response = await self.dispatch(req_id, method, params, reader=reader)
                if response is None:
                    break  # Client disconnected during execution
                writer.write(proto.encode(response))
                await writer.drain()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("Error handling client: %s", e)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def dispatch(
        self, req_id: str, method: str, params: dict, reader=None,
    ) -> dict | None:
        loop = asyncio.get_event_loop()

        try:
            if method == proto.DAEMON_STOP:
                self.shutdown_event.set()
                return proto.make_response(req_id, {"message": "shutting down"})

            elif method == proto.SESSION_CREATE:
                session = await loop.run_in_executor(
                    self.executor,
                    lambda: self.state.create_session(
                        server_url=params["server_url"],
                        token=params["token"],
                        notebook_path=params["notebook_path"],
                        name=params.get("name"),
                        kernel_name=params.get("kernel_name", "python3"),
                    ),
                )
                return proto.make_response(req_id, session.to_info())

            elif method == proto.SESSION_LIST:
                return proto.make_response(req_id, self.state.list_sessions())

            elif method == proto.SESSION_CLOSE:
                await loop.run_in_executor(
                    self.executor,
                    lambda: self.state.close_session(params["session_id"]),
                )
                return proto.make_response(req_id, {"closed": params["session_id"]})

            elif method == proto.EXEC:
                session = self.state.get_session(params["session_id"])
                result = await self._exec_with_disconnect(
                    session, params["code"], reader,
                )
                if result is None:
                    return None  # Client disconnected
                return proto.make_response(req_id, result)

            elif method == proto.INTERRUPT:
                session = self.state.get_session(params["session_id"])
                await loop.run_in_executor(
                    self.executor,
                    lambda: session.interrupt(),
                )
                return proto.make_response(req_id, {"interrupted": params["session_id"]})

            else:
                return proto.make_error(req_id, f"Unknown method: {method}")

        except KeyError as e:
            return proto.make_error(req_id, str(e))
        except ValueError as e:
            return proto.make_error(req_id, str(e))
        except Exception as e:
            logger.exception("Error in dispatch: %s", e)
            return proto.make_error(req_id, f"{type(e).__name__}: {e}")

    async def _exec_with_disconnect(self, session, code, reader):
        """Execute code, auto-interrupting if the client disconnects.

        Returns the execution result dict, or None if the client disconnected.
        """
        loop = asyncio.get_event_loop()
        exec_future = loop.run_in_executor(
            self.executor, lambda: session.execute(code),
        )

        if reader is None:
            return await exec_future

        # Race execution against client socket EOF
        disconnect = asyncio.ensure_future(reader.read(1))
        done, _ = await asyncio.wait(
            {exec_future, disconnect},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if exec_future in done:
            disconnect.cancel()
            return exec_future.result()

        # reader.read returned — check if it's truly EOF
        data = disconnect.result()
        if data:
            # Client sent unexpected data (not a disconnect); wait for exec
            return await exec_future

        # Client disconnected — interrupt kernel and let execution wind down
        logger.info("Client disconnected during exec, interrupting kernel")
        try:
            await loop.run_in_executor(self.executor, session.interrupt)
        except Exception:
            pass
        try:
            await asyncio.wait_for(exec_future, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
        return None

    async def run(self) -> None:
        sock = socket_path()
        # Clean up stale socket
        sock.unlink(missing_ok=True)

        server = await asyncio.start_unix_server(self.handle_client, path=str(sock))
        logger.info("Daemon listening on %s", sock)

        # Wait for shutdown signal
        await self.shutdown_event.wait()

        logger.info("Shutting down...")
        server.close()
        await server.wait_closed()
        self.state.close_all()
        self.executor.shutdown(wait=False)
        sock.unlink(missing_ok=True)
        logger.info("Daemon stopped.")
