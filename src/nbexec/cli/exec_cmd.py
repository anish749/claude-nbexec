import sys
from pathlib import Path

import click
import nbformat

from nbexec import protocol as proto
from .client import send_to_daemon


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


def _write_output_notebook(out_nb, output_path):
    """Write a notebook to disk and report the path on stderr."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        nbformat.write(out_nb, f)
    click.echo(f"Output notebook: {output_path}", err=True)


def _exec_notebook(session_id, notebook_path, timeout, from_cell, to_cell, output_path):
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
    is_partial = from_cell is not None or to_cell is not None

    if start >= total:
        click.echo(f"--from-cell {from_cell} is beyond the {total} code cells in the notebook", err=True)
        sys.exit(1)

    selected = code_cells[start:end]
    if not selected:
        click.echo("No code cells in the specified range", err=True)
        sys.exit(1)

    # Determine output notebook base and path
    write_output = output_path is not None or not is_partial
    if write_output:
        if output_path is None:
            # Auto-generate: input_out.ipynb
            inp = Path(notebook_path)
            output_path = str(inp.with_name(f"{inp.stem}_out{inp.suffix}"))

        # For partial runs with an existing output file, use it as the base
        # so outputs from prior runs are preserved.
        if is_partial and Path(output_path).exists():
            out_nb = nbformat.read(output_path, as_version=4)
        else:
            out_nb = nbformat.read(notebook_path, as_version=4)

        # Build a map from code cell source to indices in out_nb for updating outputs
        out_code_indices = [
            i for i, c in enumerate(out_nb.cells)
            if c.cell_type == "code" and c.source.strip()
        ]

    for i, cell in enumerate(selected, start + 1):
        click.echo(f"--- cell {i}/{total} ---", err=True)
        result = _exec_one(session_id, cell.source, timeout)

        if write_output:
            # Map the code cell index (1-based i, 0-based i-1) to out_nb cell index
            out_cell_idx = out_code_indices[i - 1]
            out_nb.cells[out_cell_idx].outputs = [
                _to_nb_output(o) for o in result.get("outputs", [])
            ]
            ec = result.get("execution_count")
            if ec is not None:
                out_nb.cells[out_cell_idx].execution_count = ec

        if result.get("status") == "error":
            if write_output:
                _write_output_notebook(out_nb, output_path)
            click.echo(f"Cell {i} failed, stopping.", err=True)
            sys.exit(1)

    if write_output:
        _write_output_notebook(out_nb, output_path)


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
    if (from_cell or to_cell) and (file_path is None or not file_path.endswith(".ipynb")):
        click.echo("--from-cell and --to-cell can only be used with .ipynb files", err=True)
        sys.exit(1)

    if output_path and (file_path is None or not file_path.endswith(".ipynb")):
        click.echo("--output can only be used with .ipynb files", err=True)
        sys.exit(1)

    if code is None and file_path is None:
        # Read from stdin
        if sys.stdin.isatty():
            click.echo("Error: provide --code, --file, or pipe code via stdin", err=True)
            sys.exit(1)
        code = sys.stdin.read()
    elif file_path is not None:
        if file_path.endswith(".ipynb"):
            _exec_notebook(session_id, file_path, timeout, from_cell, to_cell, output_path)
            return
        code = Path(file_path).read_text()

    result = _exec_one(session_id, code, timeout)
    if result.get("status") == "error":
        sys.exit(1)
