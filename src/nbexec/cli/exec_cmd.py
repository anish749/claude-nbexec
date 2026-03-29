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


def _exec_notebook(session_id, notebook_path, timeout):
    """Execute all code cells from a .ipynb file sequentially."""
    nb = nbformat.read(notebook_path, as_version=4)
    code_cells = [c for c in nb.cells if c.cell_type == "code" and c.source.strip()]
    if not code_cells:
        click.echo("No code cells found in notebook", err=True)
        sys.exit(1)

    for i, cell in enumerate(code_cells, 1):
        click.echo(f"--- cell {i}/{len(code_cells)} ---", err=True)
        ok = _exec_one(session_id, cell.source, timeout)
        if not ok:
            click.echo(f"Cell {i} failed, stopping.", err=True)
            sys.exit(1)


@click.command()
@click.option("--session", "session_id", required=True, help="Session ID")
@click.option("--code", default=None, help="Code to execute")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True), help="File containing code to execute (.py or .ipynb)")
@click.option("--timeout", default=None, type=float, help="Execution timeout in seconds (default: no timeout)")
def exec_code(session_id, code, file_path, timeout):
    """Execute code on a remote kernel."""
    if code is None and file_path is None:
        # Read from stdin
        if sys.stdin.isatty():
            click.echo("Error: provide --code, --file, or pipe code via stdin", err=True)
            sys.exit(1)
        code = sys.stdin.read()
    elif file_path is not None:
        if file_path.endswith(".ipynb"):
            _exec_notebook(session_id, file_path, timeout)
            return
        code = Path(file_path).read_text()

    ok = _exec_one(session_id, code, timeout)
    if not ok:
        sys.exit(1)
