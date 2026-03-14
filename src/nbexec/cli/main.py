import sys

import click

from .daemon_cmds import daemon
from .session_cmds import session
from .exec_cmd import exec_code

USAGE = """\
nbexec — CLI daemon that proxies code execution to remote Jupyter kernels
with local notebook logging.

Designed for AI agent use. An agent sends code strings to a remote Jupyter
kernel (e.g. PySpark, Python) and gets text results back. All executed code
and outputs are recorded in a local .ipynb file for human inspection.

Architecture: a background daemon holds persistent WebSocket connections to
remote Jupyter servers. CLI commands talk to the daemon via a Unix socket.
Multiple sessions can run simultaneously, each connected to a different
(or the same) Jupyter server with its own kernel and notebook file.

Usage:
  nbexec <command> [options]

Commands:

  daemon start
      Start the nbexec daemon in the background. The daemon listens on a
      Unix socket at ~/.local/state/nbexec/nbexec.sock and manages all
      kernel connections. Idempotent — prints a message if already running.

      Example:
        nbexec daemon start

  daemon stop
      Stop the daemon. Closes all sessions (shutting down remote kernels),
      saves all notebooks, removes the socket and PID file.

      Example:
        nbexec daemon stop

  daemon status
      Check if the daemon is running. Prints PID and socket path if running.

      Example:
        nbexec daemon status

  session create
      Create a new session: connects to a remote Jupyter server, starts a
      kernel, and creates a local .ipynb notebook file. The session ID is
      used in subsequent exec and close commands.

      Options:
        --server URL       Jupyter server URL (required, e.g. http://localhost:8888)
        --token TOKEN      Jupyter server auth token (required)
        --notebook PATH    Local path for the .ipynb log file (required)
        --name NAME        Session name/ID (optional, auto-generated if omitted)
        --kernel NAME      Kernel name (default: python3)

      Examples:
        nbexec session create --server http://localhost:8888 --token abc123 \\
            --notebook ./spark_session.ipynb --name spark
        nbexec session create --server http://localhost:9999 --token xyz \\
            --notebook ./analysis.ipynb --name analysis

  session list
      List all active sessions. Shows session ID, server URL, cell count,
      and notebook path for each session.

      Example:
        nbexec session list

  session close
      Close a session: shuts down the remote kernel, saves the notebook
      file, and removes the session from the daemon.

      Options:
        --session ID       Session ID to close (required)

      Example:
        nbexec session close --session spark

  exec
      Execute code on a remote kernel. Sends the code string to the kernel,
      waits for completion, prints the output to stdout, and records the
      cell and outputs in the session's notebook file.

      Exit code is 0 on success, 1 on execution error.

      Options:
        --session ID       Session ID (required)
        --file PATH        File containing code to execute (recommended)
        --code CODE        Code string to execute (simple one-liners only)
        --timeout SECONDS  Execution timeout (default: 300)

      If neither --code nor --file is given, reads code from stdin.

      Variables persist across exec calls within the same session (same
      kernel). Each exec appends a new cell to the notebook.

      IMPORTANT — how to send code:

        Prefer --file for anything beyond a trivial one-liner. Write the
        code to a temporary file first, then pass the path. This avoids
        bash escaping issues with quotes, newlines, and special characters
        that are common in Python/SQL code.

        Use --code only for simple single-line expressions like:
          nbexec exec --session spark --code "df.show()"
          nbexec exec --session spark --code "print(x)"

        For multiline code, write to a file first, then use --file:
          nbexec exec --session spark --file /tmp/cell.py

Agent Workflow Examples:

  Start a session and run queries interactively:
    nbexec daemon start
    nbexec session create --server http://localhost:8888 --token $TOKEN \\
        --notebook ./session.ipynb --name spark
    nbexec exec --session spark --code "df.show()"
    nbexec exec --session spark --file /tmp/query.py --timeout 120
    nbexec session close --session spark
    nbexec daemon stop

  Inspect what was executed:
    Open the .ipynb file in VS Code or Jupyter to see all cells and outputs.
    The notebook is updated after every exec call.

Runtime:
  PID file:    ~/.local/state/nbexec/daemon.pid
  Unix socket: ~/.local/state/nbexec/nbexec.sock
  Log file:    ~/.local/state/nbexec/daemon.log
"""


class NbexecGroup(click.Group):
    def format_help(self, ctx, formatter):
        formatter.write(USAGE)


@click.group(cls=NbexecGroup)
def cli():
    pass


cli.add_command(daemon)
cli.add_command(session)
cli.add_command(exec_code, name="exec")
