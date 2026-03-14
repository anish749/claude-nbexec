import click

from .daemon_cmds import daemon
from .session_cmds import session
from .exec_cmd import exec_code


@click.group()
def cli():
    """nbexec — Execute code on remote Jupyter kernels with local notebook logging."""
    pass


cli.add_command(daemon)
cli.add_command(session)
cli.add_command(exec_code, name="exec")
