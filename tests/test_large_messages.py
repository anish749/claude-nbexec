"""Round-trip tests for messages above asyncio's default 64 KiB stream limit."""

import asyncio
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nbexec import protocol as proto
from nbexec.cli.client import _send
from nbexec.daemon.server import DaemonServer

OVER_LIMIT = 200 * 1024


@pytest.fixture
def short_tmp_dir():
    """A temp dir short enough for a unix socket path (macOS caps sun_path at 104)."""
    d = tempfile.mkdtemp(dir="/tmp")
    try:
        yield Path(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
async def running_daemon(short_tmp_dir):
    """Start a DaemonServer on a temp unix socket and yield (socket path, server)."""
    sock = short_tmp_dir / "nbexec.sock"
    server = DaemonServer()

    with patch("nbexec.daemon.server.socket_path", return_value=sock):
        run_task = asyncio.ensure_future(server.run())
        for _ in range(100):
            if sock.exists():
                break
            await asyncio.sleep(0.01)
        assert sock.exists(), "daemon socket never appeared"

        try:
            yield sock, server
        finally:
            server.shutdown_event.set()
            await run_task
            server.executor.shutdown(wait=False)


@pytest.mark.asyncio
async def test_large_request_and_response_round_trip(running_daemon):
    """A >64 KiB request produces a >64 KiB response without a stream error."""
    sock, server = running_daemon

    code = "x = '" + "a" * OVER_LIMIT + "'"
    session = MagicMock()
    session.execute = MagicMock(side_effect=lambda c: {
        "status": "ok",
        "execution_count": 1,
        "cell_index": 0,
        "outputs": [{"output_type": "stream", "name": "stdout", "text": c}],
        "text": c,
    })

    request = proto.make_request(proto.EXEC, {"session_id": "s1", "code": code})

    with patch.object(server.state, "get_session", return_value=session):
        response = await _send(str(sock), request, timeout=10)

    assert response["ok"] is True
    session.execute.assert_called_once_with(code)
    assert response["result"]["text"] == code
    assert len(proto.encode(response)) > 2 * OVER_LIMIT
