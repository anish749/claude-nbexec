from pathlib import Path
from datetime import datetime, timezone

from jupyter_kernel_client import KernelClient

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
        self.kernel = KernelClient(
            server_url=self.server_url,
            token=self.token,
        )
        self.kernel.start(kernel_name=self.kernel_name)

    def execute(self, code: str) -> dict:
        if self.kernel is None or self.notebook is None:
            raise RuntimeError("Session not started")

        cell_index = self.notebook.add_cell(code)
        self._execution_count += 1

        try:
            reply = self.kernel.execute(code)
        except Exception as e:
            error_output = {
                "output_type": "error",
                "ename": type(e).__name__,
                "evalue": str(e),
                "traceback": [str(e)],
            }
            self.notebook.set_outputs(cell_index, [error_output])
            self.notebook.set_execution_count(cell_index, self._execution_count)
            self.notebook.flush()
            return {
                "status": "error",
                "execution_count": self._execution_count,
                "cell_index": cell_index,
                "outputs": [error_output],
                "text": str(e),
            }

        outputs = self._extract_outputs(reply)
        self.notebook.set_outputs(cell_index, outputs)
        self.notebook.set_execution_count(cell_index, self._execution_count)
        self.notebook.flush()

        text = self._outputs_to_text(outputs)
        status = reply.get("status", "ok") if isinstance(reply, dict) else "ok"

        return {
            "status": status,
            "execution_count": self._execution_count,
            "cell_index": cell_index,
            "outputs": outputs,
            "text": text,
        }

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
    def _extract_outputs(reply) -> list[dict]:
        """Extract outputs from jupyter-kernel-client reply."""
        # jupyter-kernel-client returns different structures depending on version.
        # Handle both dict-based and object-based replies.
        if isinstance(reply, dict):
            # Direct dict with outputs key
            if "outputs" in reply:
                return reply["outputs"]
            # Content might have stdout/stderr or data
            content = reply.get("content", reply)
            outputs = []
            if "text" in content:
                outputs.append({
                    "output_type": "stream",
                    "name": "stdout",
                    "text": content["text"],
                })
            if "data" in content:
                outputs.append({
                    "output_type": "execute_result",
                    "data": content["data"],
                    "metadata": content.get("metadata", {}),
                })
            return outputs

        # Object with attributes — adapt as needed
        outputs = []
        if hasattr(reply, "outputs"):
            return list(reply.outputs)
        if hasattr(reply, "text") and reply.text:
            outputs.append({
                "output_type": "stream",
                "name": "stdout",
                "text": reply.text,
            })
        return outputs

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
