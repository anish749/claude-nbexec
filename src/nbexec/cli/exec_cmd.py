import sys
from pathlib import Path

import click
import nbformat

from nbexec import protocol as proto
from .client import send_to_daemon


def _fail(message):
    click.echo(message, err=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Single-cell execution
# ---------------------------------------------------------------------------

def _exec_one(session_id, code, timeout):
    """Execute a single code string and print output. Returns the result dict."""
    result = send_to_daemon(
        proto.EXEC,
        {"session_id": session_id, "code": code},
        timeout=timeout,
    )
    text = result.get("text", "")
    if text:
        click.echo(text)
    return result


# ---------------------------------------------------------------------------
# Notebook cell selection
# ---------------------------------------------------------------------------

def _parse_code_cells(notebook_path):
    """Read a notebook and return (code_cells, total_count)."""
    nb = nbformat.read(notebook_path, as_version=4)
    code_cells = [c for c in nb.cells if c.cell_type == "code" and c.source.strip()]
    if not code_cells:
        _fail("No code cells found in notebook")
    return code_cells, len(code_cells)


def _select_range(code_cells, total, from_cell, to_cell):
    """Apply --from-cell/--to-cell (1-based, inclusive) and return (start_index, selected)."""
    start = (from_cell or 1) - 1
    end = to_cell or total

    if start >= total:
        _fail(f"--from-cell {from_cell} is beyond the {total} code cells in the notebook")

    selected = code_cells[start:end]
    if not selected:
        _fail("No code cells in the specified range")

    return start, selected


# ---------------------------------------------------------------------------
# Cell execution loop
# ---------------------------------------------------------------------------

def _run_cells(session_id, selected, start, total, timeout):
    """Execute cells sequentially. Returns list of (1-based cell index, result).

    Stops after the first cell that returns an error status.
    """
    results = []
    for i, cell in enumerate(selected, start + 1):
        click.echo(f"--- cell {i}/{total} ---", err=True)
        result = _exec_one(session_id, cell.source, timeout)
        results.append((i, result))
        if result.get("status") == "error":
            click.echo(f"Cell {i} failed, stopping.", err=True)
            break
    return results


# ---------------------------------------------------------------------------
# Output notebook
# ---------------------------------------------------------------------------

def _resolve_output_path(output_path, notebook_path, is_partial):
    """Return the resolved output path, or None when no output should be written."""
    if output_path:
        return output_path
    if is_partial:
        return None
    inp = Path(notebook_path)
    return str(inp.with_name(f"{inp.stem}_out{inp.suffix}"))


def _load_output_base(output_path, notebook_path, is_partial):
    """Load the base notebook for output.

    For partial runs, prefer the existing output file so prior results are preserved.
    """
    if is_partial and Path(output_path).exists():
        return nbformat.read(output_path, as_version=4)
    return nbformat.read(notebook_path, as_version=4)


def _record_results(out_nb, results):
    """Write execution results into the matching code cells of out_nb."""
    code_cell_indices = [
        i for i, c in enumerate(out_nb.cells)
        if c.cell_type == "code" and c.source.strip()
    ]
    for cell_num, result in results:
        cell = out_nb.cells[code_cell_indices[cell_num - 1]]
        cell.outputs = [_to_nb_output(o) for o in result.get("outputs", [])]
        ec = result.get("execution_count")
        if ec is not None:
            cell.execution_count = ec


def _write_output_notebook(out_nb, output_path):
    """Write a notebook to disk and report the path on stderr."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        nbformat.write(out_nb, f)
    click.echo(f"Output notebook: {output_path}", err=True)


def _to_nb_output(output):
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
        return nbformat.v4.new_output(
            output_type=otype,
            data=output.get("data", {}),
            metadata=output.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Notebook orchestrator
# ---------------------------------------------------------------------------

def _exec_notebook(session_id, notebook_path, timeout, from_cell, to_cell, output_path):
    """Execute code cells from a .ipynb file sequentially."""
    code_cells, total = _parse_code_cells(notebook_path)
    start, selected = _select_range(code_cells, total, from_cell, to_cell)
    is_partial = from_cell is not None or to_cell is not None

    results = _run_cells(session_id, selected, start, total, timeout)

    output_path = _resolve_output_path(output_path, notebook_path, is_partial)
    if output_path:
        out_nb = _load_output_base(output_path, notebook_path, is_partial)
        _record_results(out_nb, results)
        _write_output_notebook(out_nb, output_path)

    if results and results[-1][1].get("status") == "error":
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

@click.command()
@click.option("--session", "session_id", required=True, help="Session ID")
@click.option("--code", default=None, help="Code to execute")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True), help="File containing code to execute (.py or .ipynb)")
@click.option("--timeout", default=None, type=float, help="Execution timeout in seconds (default: no timeout)")
@click.option("--from-cell", "from_cell", default=None, type=int, help="Start from this code cell (1-based, inclusive). Only for .ipynb files.")
@click.option("--to-cell", "to_cell", default=None, type=int, help="Stop at this code cell (1-based, inclusive). Only for .ipynb files.")
@click.option("--output", "output_path", default=None, type=click.Path(), help="Output notebook path. Only for .ipynb files.")
def exec_code(session_id, code, file_path, timeout, from_cell, to_cell, output_path):
    """Execute code on a remote kernel."""
    is_notebook = file_path is not None and file_path.endswith(".ipynb")

    if (from_cell or to_cell) and not is_notebook:
        _fail("--from-cell and --to-cell can only be used with .ipynb files")
    if output_path and not is_notebook:
        _fail("--output can only be used with .ipynb files")

    if is_notebook:
        _exec_notebook(session_id, file_path, timeout, from_cell, to_cell, output_path)
        return

    if code is None and file_path is None:
        if sys.stdin.isatty():
            _fail("Error: provide --code, --file, or pipe code via stdin")
        code = sys.stdin.read()
    elif file_path is not None:
        code = Path(file_path).read_text()

    result = _exec_one(session_id, code, timeout)
    if result.get("status") == "error":
        sys.exit(1)
