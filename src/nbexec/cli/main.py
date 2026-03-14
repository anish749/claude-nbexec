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

      The code can be provided via --code, --file, or piped via stdin.
      Exit code is 0 on success, 1 on execution error.

      Options:
        --session ID       Session ID (required)
        --code CODE        Code string to execute
        --file PATH        File containing code to execute
        --timeout SECONDS  Execution timeout (default: 300)

      If neither --code nor --file is given, reads code from stdin.

      Variables persist across exec calls within the same session (same
      kernel). Each exec appends a new cell to the notebook.

      Examples:
        nbexec exec --session spark --code "print('hello')"
        nbexec exec --session spark --code "df = spark.sql('SELECT count(*) FROM videos')"
        nbexec exec --session spark --code "df.show()"
        nbexec exec --session spark --file /tmp/query.py
        echo "1 + 1" | nbexec exec --session spark

Agent Workflow Examples:

  Start a session and run queries interactively:
    nbexec daemon start
    nbexec session create --server http://localhost:8888 --token $TOKEN \\
        --notebook ./session.ipynb --name spark
    nbexec exec --session spark --code "from pyspark.sql import SparkSession"
    nbexec exec --session spark --code "spark = SparkSession.builder.getOrCreate()"
    nbexec exec --session spark --code "spark.sql('SHOW TABLES').show()"
    nbexec exec --session spark --code "df = spark.sql('SELECT platform, count(*) as cnt FROM videos GROUP BY platform')"
    nbexec exec --session spark --code "df.show()"
    nbexec session close --session spark
    nbexec daemon stop

  Multiple sessions to different servers:
    nbexec daemon start
    nbexec session create --server http://localhost:8888 --token $T1 \\
        --notebook ./prod.ipynb --name prod
    nbexec session create --server http://localhost:9999 --token $T2 \\
        --notebook ./staging.ipynb --name staging
    nbexec exec --session prod --code "spark.sql('SELECT count(*) FROM videos').show()"
    nbexec exec --session staging --code "spark.sql('SELECT count(*) FROM videos').show()"
    nbexec session list
    nbexec session close --session prod
    nbexec session close --session staging
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
