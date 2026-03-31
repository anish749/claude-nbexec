from pathlib import Path
from datetime import datetime, timezone

import requests
from jupyter_kernel_client import KernelClient

from .diagnostics import diagnose_connection_error, is_connection_error
from .notebook import NotebookWriter


class Session:
    """A session owns a remote kernel connection and a local notebook file."""

    def __init__(
        self,
        session_id: str,
        server_url: str,
        token: str,
        notebook_path: Path,
        name: str | None = None,
        kernel_name: str = "python3",
    ):
        self.session_id = session_id
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.notebook_path = Path(notebook_path)
        self.name = name or session_id
        self.kernel_name = kernel_name
        self.kernel: KernelClient | None = None
        self.notebook: NotebookWriter | None = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self._execution_count = 0

    def start(self) -> None:
        self.notebook = NotebookWriter(self.notebook_path)

        # Fetch XSRF cookie from the server (needed for POST requests)
        headers = {}
        xsrf_cookie = self._fetch_xsrf_cookie()
        if xsrf_cookie:
            headers["X-XSRFToken"] = xsrf_cookie
            headers["Cookie"] = f"_xsrf={xsrf_cookie}"

        self.kernel = KernelClient(
            server_url=self.server_url,
            token=self.token or None,
            headers=headers,
        )
        self.kernel.start(name=self.kernel_name)

    def _fetch_xsrf_cookie(self) -> str | None:
        """Fetch XSRF token from the Jupyter server."""
        try:
            resp = requests.get(f"{self.server_url}/tree", timeout=10)
            xsrf = resp.cookies.get("_xsrf")
            return xsrf
        except Exception:
            return None

    def execute(self, code: str) -> dict:
        if self.kernel is None or self.notebook is None:
            raise RuntimeError("Session not started")

        cell_index = self.notebook.add_cell(code)
        self._execution_count += 1

        try:
            reply = self.kernel.execute(code, timeout=None)
        except Exception as e:
            if is_connection_error(e):
                kernel_id = self.kernel.id if self.kernel else None
                message = diagnose_connection_error(
                    self.server_url, self.token, kernel_id,
                )
            else:
                message = str(e)
            error_output = {
                "output_type": "error",
                "ename": type(e).__name__,
                "evalue": message,
                "traceback": [message],
            }
            self.notebook.set_outputs(cell_index, [error_output])
            self.notebook.set_execution_count(cell_index, self._execution_count)
            self.notebook.flush()
            return {
                "status": "error",
                "execution_count": self._execution_count,
                "cell_index": cell_index,
                "outputs": [error_output],
                "text": message,
            }

        outputs = self._extract_outputs(reply)
        exec_count = reply.get("execution_count", self._execution_count)
        self.notebook.set_outputs(cell_index, outputs)
        self.notebook.set_execution_count(cell_index, exec_count)
        self.notebook.flush()

        text = self._outputs_to_text(outputs)
        status = reply.get("status", "ok")

        return {
            "status": status,
            "execution_count": exec_count,
            "cell_index": cell_index,
            "outputs": outputs,
            "text": text,
        }

    def interrupt(self) -> None:
        if self.kernel is None:
            raise RuntimeError("Session not started")
        self.kernel.interrupt()

    def close(self) -> None:
        if self.kernel is not None:
            try:
                self.kernel.stop()
            except Exception:
                pass
            self.kernel = None
        if self.notebook is not None:
            try:
                self.notebook.flush()
            except Exception:
                pass

    def to_info(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "server_url": self.server_url,
            "notebook_path": str(self.notebook_path),
            "cell_count": self.notebook.cell_count if self.notebook else 0,
            "created_at": self.created_at,
        }

    @staticmethod
    def _extract_outputs(reply: dict) -> list[dict]:
        """Extract outputs from jupyter-kernel-client reply.

        Reply format: {"execution_count": int, "status": str, "outputs": list[dict]}
        Outputs follow nbformat structure.
        """
        return reply.get("outputs", [])

    @staticmethod
    def _outputs_to_text(outputs: list[dict]) -> str:
        """Flatten outputs to plain text for CLI display."""
        parts = []
        for o in outputs:
            otype = o.get("output_type", "")
            if otype == "stream":
                parts.append(o.get("text", ""))
            elif otype == "error":
                tb = o.get("traceback", [])
                parts.append("\n".join(tb) if tb else o.get("evalue", ""))
            elif otype in ("execute_result", "display_data"):
                data = o.get("data", {})
                if "text/plain" in data:
                    parts.append(data["text/plain"])
                elif "text/html" in data:
                    parts.append(data["text/html"])
        return "\n".join(parts)
