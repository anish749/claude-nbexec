import sys
from pathlib import Path

import click

from nbexec import protocol as proto
from .client import send_to_daemon


@click.command()
@click.option("--session", "session_id", required=True, help="Session ID")
@click.option("--code", default=None, help="Code to execute")
@click.option("--file", "file_path", default=None, type=click.Path(exists=True), help="File containing code to execute")
@click.option("--timeout", default=300.0, type=float, help="Execution timeout in seconds")
def exec_code(session_id, code, file_path, timeout):
    """Execute code on a remote kernel."""
    if code is None and file_path is None:
        # Read from stdin
        if sys.stdin.isatty():
            click.echo("Error: provide --code, --file, or pipe code via stdin", err=True)
            sys.exit(1)
        code = sys.stdin.read()
    elif file_path is not None:
        code = Path(file_path).read_text()

    result = send_to_daemon(
        proto.EXEC,
        {"session_id": session_id, "code": code},
        timeout=timeout,
    )

    text = result.get("text", "")
    if text:
        click.echo(text)

    if result.get("status") == "error":
        sys.exit(1)
