import asyncio
import logging
import os
import signal
import sys
import time

from nbexec.paths import pid_path, log_path, socket_path
from .server import DaemonServer


def _setup_logging():
    lp = log_path()
    logging.basicConfig(
        filename=str(lp),
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


def _write_pid():
    pid_path().write_text(str(os.getpid()))


def _remove_pid():
    pid_path().unlink(missing_ok=True)


def daemonize() -> None:
    """Double-fork to fully detach from the terminal."""
    # First fork
    pid = os.fork()
    if pid > 0:
        # Parent waits briefly for the daemon to create its PID file
        for _ in range(20):
            if pid_path().exists():
                return
            time.sleep(0.1)
        return

    # New session
    os.setsid()

    # Second fork
    pid = os.fork()
    if pid > 0:
        os._exit(0)

    # Redirect stdio
    sys.stdin.close()
    lp = log_path()
    sys.stdout = open(lp, "a")
    sys.stderr = sys.stdout

    _setup_logging()
    _write_pid()

    def handle_sigterm(*_):
        # The asyncio event loop will pick this up
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        server = DaemonServer()
        asyncio.run(server.run())
    finally:
        _remove_pid()
        socket_path().unlink(missing_ok=True)
        os._exit(0)


def start_daemon() -> bool:
    """Start the daemon. Returns True if started, False if already running."""
    if is_daemon_running():
        return False
    # Clean stale files
    pid_path().unlink(missing_ok=True)
    socket_path().unlink(missing_ok=True)
    daemonize()
    return True


def stop_daemon() -> bool:
    """Stop the daemon via SIGTERM. Returns True if stopped."""
    pp = pid_path()
    if not pp.exists():
        return False

    pid = int(pp.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pp.unlink(missing_ok=True)
        return False

    # Wait for it to die
    for _ in range(30):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            pp.unlink(missing_ok=True)
            return True
    return False


def is_daemon_running() -> bool:
    pp = pid_path()
    if not pp.exists():
        return False
    try:
        pid = int(pp.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        pp.unlink(missing_ok=True)
        return False


def daemon_status() -> dict:
    pp = pid_path()
    if not pp.exists():
        return {"running": False}
    try:
        pid = int(pp.read_text().strip())
        os.kill(pid, 0)
        return {
            "running": True,
            "pid": pid,
            "socket": str(socket_path()),
        }
    except (ProcessLookupError, ValueError):
        pp.unlink(missing_ok=True)
        return {"running": False}
