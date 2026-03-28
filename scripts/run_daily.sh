#!/usr/bin/env sh
set -eu

# Intended for cron/VM usage.
: "${PYTHON_BIN:=python3}"
$PYTHON_BIN -m scripts.run_daily
