import os
import tempfile
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_notebook


class NotebookWriter:
    """Append-only .ipynb writer. Adds code cells and their outputs."""

    def __init__(self, path: Path):
        self.path = Path(path)
        if self.path.exists():
            with open(self.path) as f:
                self.nb = nbformat.read(f, as_version=4)
        else:
            self.nb = new_notebook()
            self.nb.metadata["kernelspec"] = {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            }
            self.flush()

    def add_cell(self, source: str) -> int:
        cell = new_code_cell(source=source)
        self.nb.cells.append(cell)
        return len(self.nb.cells) - 1

    def set_outputs(self, cell_index: int, outputs: list[dict]) -> None:
        cell = self.nb.cells[cell_index]
        cell.outputs = [self._normalize_output(o) for o in outputs]

    def set_execution_count(self, cell_index: int, count: int | None) -> None:
        if count is not None:
            self.nb.cells[cell_index].execution_count = count

    def flush(self) -> None:
        """Atomic write: write to temp file then rename."""
        dir_ = self.path.parent
        dir_.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".ipynb.tmp")
        try:
            with os.fdopen(fd, "w") as f:
                nbformat.write(self.nb, f)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @property
    def cell_count(self) -> int:
        return len(self.nb.cells)

    @staticmethod
    def _normalize_output(output: dict) -> nbformat.NotebookNode:
        """Convert a raw output dict to an nbformat output node."""
        otype = output.get("output_type", "execute_result")

        if otype == "stream":
            return nbformat.v4.new_output(
                output_type="stream",
                name=output.get("name", "stdout"),
                text=output.get("text", ""),
            )
        elif otype == "error":
            return nbformat.v4.new_output(
                output_type="error",
                ename=output.get("ename", ""),
                evalue=output.get("evalue", ""),
                traceback=output.get("traceback", []),
            )
        else:
            # execute_result or display_data
            data = output.get("data", {})
            metadata = output.get("metadata", {})
            return nbformat.v4.new_output(
                output_type=otype,
                data=data,
                metadata=metadata,
            )
