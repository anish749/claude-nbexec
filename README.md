# nbexec

[![PyPI](https://img.shields.io/pypi/v/claude-nbexec)](https://pypi.org/project/claude-nbexec/)

A CLI tool that lets AI agents (like Claude Code) execute code on remote Jupyter kernels. All executed code and outputs are logged to a local `.ipynb` notebook file for human review.

## Why

When an AI agent needs to run code on a remote compute environment — a PySpark cluster, a GPU machine, a data warehouse notebook server — there's no simple way to do it interactively. The agent can't open a Jupyter UI. It needs to send code, get results, and move on.

nbexec bridges this gap. The agent calls `nbexec exec --code "..."` and gets text output on stdout. It can also run an existing `.ipynb` notebook on the same kernel with `nbexec exec --file ./analysis.ipynb` — all code cells execute sequentially, and variables persist across all exec calls in the session. Behind the scenes, a daemon holds a persistent WebSocket connection to the remote Jupyter kernel, and every cell + output is recorded in a local `.ipynb` file that you can open in VS Code or Jupyter to see exactly what the agent did.

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

## Why a CLI and not an MCP server or raw HTTP

**Agents don't think in cells.** Existing Jupyter MCP servers expose notebook operations — create cell, edit cell, move cell, run cell. But an agent executing code on a remote kernel doesn't care about cells. It just wants to send code and get results. It doesn't need to edit cell 5 or reorder cells — if something went wrong, it sends corrected code as the next execution. nbexec matches this model: send code, get output, move on. The notebook is just a side effect for human review, not something the agent manages.

**Clean context.** An MCP server's tool definitions live in the agent's prompt at all times. nbexec adds nothing to the prompt until the agent actually needs it — the skill loads on demand, and `--help` is only fetched when invoked.

**Full visibility.** Everything inside an MCP server is opaque to the agent — it can only call the tools that are exposed. With a CLI, the agent has access to the source code, can inspect how things work, and can understand or work around issues on its own.

**Persistent connections without agent coupling.** The daemon runs as a separate process, managing WebSocket connections and kernel sessions independently. The agent doesn't need to hold connections or re-establish them between calls. Sessions survive across multiple agent conversations. An MCP server's lifecycle is tied to the agent process that started it.

**Fewer tokens than raw HTTP.** The agent could call the Jupyter REST API directly via curl, but that means generating verbose HTTP requests for every cell execution, manually managing XSRF tokens, parsing WebSocket message framing, and tracking kernel/session IDs. A single `nbexec exec --session spark --code "..."` replaces all of that. Less generated tokens, simpler logic, same result.

**Self-documenting from the CLI.** The agent runs `nbexec --help` and gets everything it needs — commands, options, examples, workflow patterns. No need to embed documentation in MCP tool descriptions or maintain it in two places.

## Inspiration

The architectural pattern — a long-lived daemon process, CLI-driven interaction, persistent state across calls, and a skill file for agent discovery — is inspired by [OpenClaw](https://github.com/openclaw/openclaw). nbexec applies the same intuition to a narrower problem: giving AI coding agents structured access to remote Jupyter kernels.

## Installation

Requires Python 3.10+.

```bash
uv tool install claude-nbexec
```

Or with pip:

```bash
pip install claude-nbexec
```

### Install the Claude Code skill

Clone the repo and run the skill installer:

```bash
git clone https://github.com/anish749/claude-nbexec.git && cd claude-nbexec
./install-skill.sh
```

This installs a skill to `$CLAUDE_CONFIG_DIR/skills/nbexec/` that teaches Claude Code when and how to use nbexec.

### Usage

All commands and options are documented in `nbexec --help`.
