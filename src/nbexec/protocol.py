import json
import uuid
from typing import Any


# Method names
DAEMON_STOP = "daemon.stop"
SESSION_CREATE = "session.create"
SESSION_LIST = "session.list"
SESSION_CLOSE = "session.close"
EXEC = "exec"


def make_request(method: str, params: dict[str, Any] | None = None) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "method": method,
        "params": params or {},
    }


def make_response(request_id: str, result: Any = None) -> dict:
    return {"id": request_id, "ok": True, "result": result}


def make_error(request_id: str, error: str) -> dict:
    return {"id": request_id, "ok": False, "error": error}


def encode(msg: dict) -> bytes:
    return json.dumps(msg).encode("utf-8") + b"\n"


def decode(line: bytes) -> dict:
    return json.loads(line.strip())
