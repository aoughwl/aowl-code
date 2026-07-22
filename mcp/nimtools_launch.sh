#!/usr/bin/env bash
# Launcher for the nimony-native MCP server (built on the aowlmcp library).
# Registered by .mcp.json as the "nimtools" server. It locates the aowlmcp
# checkout, builds the server binary on first use, and execs it so it speaks
# MCP over this process's stdio.
#
# Override the checkout location with AOWLMCP_DIR; the Nimony compiler with
# NIMONY. If the build fails, this exits non-zero and Claude Code simply treats
# the nimtools server as unavailable (the Python "nimlang" server is unaffected).
set -euo pipefail

AOWLMCP_DIR="${AOWLMCP_DIR:-$HOME/aowlmcp}"
BIN="$AOWLMCP_DIR/bin/nimtools_server"

if [[ ! -x "$BIN" ]]; then
  if [[ ! -d "$AOWLMCP_DIR" ]]; then
    echo "nimtools_launch: aowlmcp checkout not found at $AOWLMCP_DIR" >&2
    echo "  git clone https://github.com/aoughwl/aowlmcp \"$AOWLMCP_DIR\"" >&2
    exit 1
  fi
  "$AOWLMCP_DIR/build.sh" examples/nimtools_server.nim >&2
fi

exec "$BIN"
