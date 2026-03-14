import asyncio
import json
import sys

from nbexec import protocol as proto
from nbexec.paths import socket_path


def send_to_daemon(method: str, params: dict | None = None, timeout: float | None = None) -> dict:
    """Send a request to the daemon and return the response.

    Raises SystemExit on connection errors so CLI commands fail cleanly.
    """
    sock = socket_path()
    if not sock.exists():
        print("Error: daemon is not running. Start it with: nbexec daemon start", file=sys.stderr)
        sys.exit(1)

    request = proto.make_request(method, params)
    response = asyncio.run(_send(str(sock), request, timeout))

    if not response.get("ok"):
        print(f"Error: {response.get('error', 'unknown error')}", file=sys.stderr)
        sys.exit(1)

    return response["result"]


async def _send(sock_path: str, request: dict, timeout: float | None) -> dict:
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
    except (ConnectionRefusedError, FileNotFoundError):
        print("Error: cannot connect to daemon. Is it running?", file=sys.stderr)
        sys.exit(1)

    try:
        writer.write(proto.encode(request))
        await writer.drain()

        line = await asyncio.wait_for(reader.readline(), timeout=timeout)
        if not line:
            print("Error: daemon closed connection", file=sys.stderr)
            sys.exit(1)

        return proto.decode(line)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
