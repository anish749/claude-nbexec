"""Tests for daemon-side client disconnect detection during EXEC."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nbexec.daemon.server import DaemonServer


def _make_session(execute_delay=0, execute_result=None):
    """Create a mock session with configurable execute behavior."""
    if execute_result is None:
        execute_result = {
            "status": "ok",
            "execution_count": 1,
            "cell_index": 0,
            "outputs": [],
            "text": "",
        }

    session = MagicMock()

    def execute(code):
        if execute_delay:
            import time
            time.sleep(execute_delay)
        return execute_result

    session.execute = MagicMock(side_effect=execute)
    session.interrupt = MagicMock()
    return session


class TestExecWithDisconnect:
    """Test _exec_with_disconnect behavior."""

    @pytest.mark.asyncio
    async def test_exec_completes_normally(self):
        """When client stays connected, execution result is returned."""
        server = DaemonServer()
        session = _make_session()

        reader = AsyncMock()
        reader.read = AsyncMock(side_effect=asyncio.CancelledError)

        result = await server._exec_with_disconnect(session, "x = 1", reader)

        assert result["status"] == "ok"
        session.execute.assert_called_once_with("x = 1")
        session.interrupt.assert_not_called()
        server.executor.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_client_disconnect_triggers_interrupt(self):
        """When client socket closes during exec, kernel is interrupted."""
        server = DaemonServer()
        session = _make_session(execute_delay=0.5)

        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"")

        result = await server._exec_with_disconnect(session, "x = 1", reader)

        assert result is None
        session.interrupt.assert_called_once()
        server.executor.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_no_reader_skips_disconnect_check(self):
        """When reader is None, execution runs without disconnect detection."""
        server = DaemonServer()
        session = _make_session()

        result = await server._exec_with_disconnect(session, "x = 1", None)

        assert result["status"] == "ok"
        session.execute.assert_called_once_with("x = 1")
        server.executor.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_unexpected_data_not_treated_as_disconnect(self):
        """If reader returns data (not EOF), wait for exec to finish."""
        server = DaemonServer()
        session = _make_session(execute_delay=0.2)

        reader = AsyncMock()
        reader.read = AsyncMock(return_value=b"{")

        result = await server._exec_with_disconnect(session, "x = 1", reader)

        assert result["status"] == "ok"
        session.interrupt.assert_not_called()
        server.executor.shutdown(wait=False)


class TestDispatchDisconnect:
    """Test that dispatch returns None on client disconnect during EXEC."""

    @pytest.mark.asyncio
    async def test_dispatch_returns_none_on_disconnect(self):
        """dispatch returns None when client disconnects during EXEC."""
        server = DaemonServer()
        session = _make_session(execute_delay=0.5)

        with patch.object(server.state, "get_session", return_value=session):
            reader = AsyncMock()
            reader.read = AsyncMock(return_value=b"")

            response = await server.dispatch(
                "req1", "exec",
                {"session_id": "s1", "code": "x = 1"},
                reader=reader,
            )

        assert response is None
        session.interrupt.assert_called_once()
        server.executor.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_dispatch_returns_response_normally(self):
        """dispatch returns normal response when client stays connected."""
        server = DaemonServer()
        session = _make_session()

        with patch.object(server.state, "get_session", return_value=session):
            reader = AsyncMock()
            reader.read = AsyncMock(side_effect=asyncio.CancelledError)

            response = await server.dispatch(
                "req1", "exec",
                {"session_id": "s1", "code": "x = 1"},
                reader=reader,
            )

        assert response["ok"] is True
        assert response["result"]["status"] == "ok"
        server.executor.shutdown(wait=False)
