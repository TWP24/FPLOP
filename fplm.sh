#!/bin/sh
# Convenience wrapper so you don't have to remember the venv path.
exec "$(dirname "$0")/.venv/bin/python" -m fplm.cli "$@"
