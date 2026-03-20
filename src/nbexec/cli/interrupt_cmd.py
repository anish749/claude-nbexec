import click

from nbexec import protocol as proto
from .client import send_to_daemon


@click.command()
@click.option("--session", "session_id", required=True, help="Session ID")
def interrupt(session_id):
    """Interrupt a running execution on a remote kernel."""
    send_to_daemon(proto.INTERRUPT, {"session_id": session_id})
    click.echo(f"Interrupt sent to session '{session_id}'.")
