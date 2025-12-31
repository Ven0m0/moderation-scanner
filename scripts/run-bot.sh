#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
export PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=0 PYTHONOPTIMIZE=2 PYTHONFAULTHANDLER=0 \
  PYTHONIOENCODING=utf-8 PYTHONMALLOCSTATS=0 DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8

has(){ command -v -- "$1" &>/dev/null; }
die(){ printf '%s\n' "$1" >&2; exit 1; }
has python3 || die "python3 not found"

# Change to repository root
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR/.."

readonly CREDS="${XDG_CONFIG_HOME:-$HOME/.config}/account_scanner/credentials"
[[ -f $CREDS ]] && source "$CREDS"
[[ -z ${DISCORD_BOT_TOKEN:-} ]] && die "DISCORD_BOT_TOKEN not set"
mkdir -p scans
exec python3 discord_bot.py
