import secrets
from pathlib import Path

from nbexec.session.manager import Session


class DaemonState:
    """Registry of active sessions."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}

    def create_session(
        self,
        server_url: str,
        token: str,
        notebook_path: str,
        name: str | None = None,
        kernel_name: str = "python3",
    ) -> Session:
        session_id = name or secrets.token_hex(4)
        if session_id in self.sessions:
            raise ValueError(f"Session '{session_id}' already exists")

        session = Session(
            session_id=session_id,
            server_url=server_url,
            token=token,
            notebook_path=Path(notebook_path),
            name=name,
            kernel_name=kernel_name,
        )
        session.start()
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session:
        if session_id not in self.sessions:
            raise KeyError(f"Session '{session_id}' not found")
        return self.sessions[session_id]

    def list_sessions(self) -> list[dict]:
        return [s.to_info() for s in self.sessions.values()]

    def close_session(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session is None:
            raise KeyError(f"Session '{session_id}' not found")
        session.close()

    def close_all(self) -> None:
        for session in self.sessions.values():
            session.close()
        self.sessions.clear()
