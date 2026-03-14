import json
import click

from nbexec.daemon.process import start_daemon, stop_daemon, daemon_status


@click.group()
def daemon():
    """Manage the nbexec daemon."""
    pass


@daemon.command()
def start():
    """Start the daemon in the background."""
    if start_daemon():
        click.echo("Daemon started.")
    else:
        click.echo("Daemon is already running.")


@daemon.command()
def stop():
    """Stop the daemon."""
    if stop_daemon():
        click.echo("Daemon stopped.")
    else:
        click.echo("Daemon is not running.")


@daemon.command()
def status():
    """Check daemon status."""
    info = daemon_status()
    if info["running"]:
        click.echo(f"Running (pid={info['pid']}, socket={info['socket']})")
    else:
        click.echo("Not running.")
