from pathlib import Path


def runtime_dir() -> Path:
    d = Path.home() / ".local" / "state" / "nbexec"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pid_path() -> Path:
    return runtime_dir() / "daemon.pid"


def socket_path() -> Path:
    return runtime_dir() / "nbexec.sock"


def log_path() -> Path:
    return runtime_dir() / "daemon.log"
