# nbexec

A CLI tool that lets AI agents (like Claude Code) execute code on remote Jupyter kernels. All executed code and outputs are logged to a local `.ipynb` notebook file for human review.

## Why

When an AI agent needs to run code on a remote compute environment — a PySpark cluster, a GPU machine, a data warehouse notebook server — there's no simple way to do it interactively. The agent can't open a Jupyter UI. It needs to send code, get results, and move on.

nbexec bridges this gap. The agent calls `nbexec exec --code "..."` and gets text output on stdout. Behind the scenes, a daemon holds a persistent WebSocket connection to the remote Jupyter kernel, and every cell + output is recorded in a local `.ipynb` file that you can open in VS Code or Jupyter to see exactly what the agent did.

## How it works

```
Agent (Claude Code)              nbexec daemon                Remote Jupyter Server
───────────────────              ─────────────                ─────────────────────
                                 (background process)

exec --code "..."  ────────────► Unix socket request
                                 append cell to .ipynb
                                 send to kernel via WS ─────► kernel executes code
                                                         ◄─── results on iopub
                                 write output to .ipynb
stdout: result     ◄──────────── return output
```

The daemon is a long-running background process that holds persistent WebSocket connections to one or more remote Jupyter servers. CLI commands (`exec`, `session create`, etc.) are thin clients that talk to the daemon over a Unix socket — each `exec` is a synchronous request/response.

This is the same protocol VS Code uses when you connect a local notebook to a remote Jupyter server. The notebook document stays local, only code strings are sent to the kernel. nbexec replicates this model for CLI/agent use, using [jupyter-kernel-client](https://github.com/datalayer/jupyter-kernel-client) to manage the kernel connection.

## Installation

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url> && cd claude-nbexec
uv sync
```

### Install the Claude Code skill

```bash
./install-skill.sh
```

This installs a skill to `$CLAUDE_CONFIG_DIR/skills/nbexec/` that teaches Claude Code when and how to use nbexec.

### Usage

All commands and options are documented in `nbexec --help`.
