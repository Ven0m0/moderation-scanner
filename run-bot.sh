#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t' LC_ALL=C

has(){ command -v -- "$1" &>/dev/null; }
die(){ printf '%s\n' "$1" >&2; exit 1; }

has python3 || die "python3 not found"

readonly CREDS="${XDG_CONFIG_HOME:-$HOME/.config}/account_scanner/credentials"
[[ -f $CREDS ]] && source "$CREDS"

[[ -z ${DISCORD_BOT_TOKEN:-} ]] && die "DISCORD_BOT_TOKEN not set"

mkdir -p scans
exec python3 discord_bot.py
