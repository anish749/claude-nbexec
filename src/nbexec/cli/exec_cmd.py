import sys
from pathlib import Path

import click
import nbformat

from nbexec import protocol as proto
from .client import send_to_daemon


def _exec_one(session_id, code, timeout):
    """Execute a single code string and print output. Returns True on success."""
    result = send_to_daemon(
        proto.EXEC,
        {"session_id": session_id, "code": code},
        timeout=timeout,
    )
    text = result.get("text", "")
    if text:
        click.echo(text)
    return result.get("status") != "error"


def _exec_notebook(session_id, notebook_path, timeout, from_cell, to_cell):
    """Execute code cells from a .ipynb file sequentially."""
    nb = nbformat.read(notebook_path, as_version=4)
    code_cells = [c for c in nb.cells if c.cell_type == "code" and c.source.strip()]
    total = len(code_cells)
    if not code_cells:
        click.echo("No code cells found in notebook", err=True)
        sys.exit(1)

    # --from-cell and --to-cell are 1-based, inclusive
    start = (from_cell or 1) - 1
    end = to_cell or total

    if start >= total:
        click.echo(f"--from-cell {from_cell} is beyond the {total} code cells in the notebook", err=True)
        sys.exit(1)

    selected = code_cells[start:end]
    if not selected:
        click.echo("No code cells in the specified range", err=True)
        sys.exit(1)

    for i, cell in enumerate(selected, start + 1):
        click.echo(f"--- cell {i}/{total} ---", err=True)
        ok = _exec_one(session_id, cell.source, timeout)
        if not ok:
            click.echo(f"Cell {i} failed, stopping.", err=True)
            sys.exit(1)


@click.command()
@click.option("--session", "session_id", required=True, help="Session ID")
@click.option("--code", default=None, help="Code to execute")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True), help="File containing code to execute (.py or .ipynb)")
@click.option("--timeout", default=None, type=float, help="Execution timeout in seconds (default: no timeout)")
@click.option("--from-cell", "from_cell", default=None, type=int, help="Start from this code cell (1-based, inclusive). Only for .ipynb files.")
@click.option("--to-cell", "to_cell", default=None, type=int, help="Stop at this code cell (1-based, inclusive). Only for .ipynb files.")
def exec_code(session_id, code, file_path, timeout, from_cell, to_cell):
    """Execute code on a remote kernel."""
    if (from_cell or to_cell) and (file_path is None or not file_path.endswith(".ipynb")):
        click.echo("--from-cell and --to-cell can only be used with .ipynb files", err=True)
        sys.exit(1)

    if code is None and file_path is None:
        # Read from stdin
        if sys.stdin.isatty():
            click.echo("Error: provide --code, --file, or pipe code via stdin", err=True)
            sys.exit(1)
        code = sys.stdin.read()
    elif file_path is not None:
        if file_path.endswith(".ipynb"):
            _exec_notebook(session_id, file_path, timeout, from_cell, to_cell)
            return
        code = Path(file_path).read_text()

    ok = _exec_one(session_id, code, timeout)
    if not ok:
        sys.exit(1)
