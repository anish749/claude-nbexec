import click

from nbexec import protocol as proto
from .client import send_to_daemon


@click.group()
def session():
    """Manage kernel sessions."""
    pass


@session.command()
@click.option("--server", required=True, help="Jupyter server URL (e.g. http://localhost:8888)")
@click.option("--token", required=True, help="Jupyter server token")
@click.option("--notebook", required=True, help="Path for the local .ipynb file")
@click.option("--name", default=None, help="Session name (auto-generated if omitted)")
@click.option("--kernel", "kernel_name", default="python3", help="Kernel name")
def create(server, token, notebook, name, kernel_name):
    """Create a new session connected to a remote Jupyter server."""
    result = send_to_daemon(proto.SESSION_CREATE, {
        "server_url": server,
        "token": token,
        "notebook_path": notebook,
        "name": name,
        "kernel_name": kernel_name,
    })
    click.echo(f"Session created: {result['session_id']}")
    click.echo(f"  Name:     {result['name']}")
    click.echo(f"  Server:   {result['server_url']}")
    click.echo(f"  Notebook: {result['notebook_path']}")


@session.command("list")
def list_sessions():
    """List active sessions."""
    sessions = send_to_daemon(proto.SESSION_LIST)
    if not sessions:
        click.echo("No active sessions.")
        return
    for s in sessions:
        click.echo(
            f"  {s['session_id']:<20s} {s['server_url']:<30s} "
            f"cells={s['cell_count']:<4d} {s['notebook_path']}"
        )


@session.command()
@click.option("--session", "session_id", required=True, help="Session ID to close")
def close(session_id):
    """Close a session and its remote kernel."""
    send_to_daemon(proto.SESSION_CLOSE, {"session_id": session_id})
    click.echo(f"Session '{session_id}' closed.")
