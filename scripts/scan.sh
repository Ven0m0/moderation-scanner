#!/usr/bin/env bash
# shellcheck enable=all shell=bash source-path=SCRIPTDIR
set -euo pipefail; shopt -s nullglob globstar
IFS=$'\n\t' LC_ALL=C

has(){ command -v -- "$1" &>/dev/null; }
err(){ printf '%s\n' "$*" >&2; }
die(){ err "$@"; exit 1; }

readonly SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCANNER="${SCRIPT_DIR}/../account_scanner.py"
readonly CREDS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/account_scanner/credentials"

[[ -f $SCANNER ]] || die "Scanner not found: $SCANNER"
has python3 || die "python3 not found in PATH"

if [[ -f $CREDS_FILE ]]; then
  # shellcheck source=/dev/null
  source "$CREDS_FILE" || err "Warning: Failed to source $CREDS_FILE"
fi

args=()
[[ ${PERSPECTIVE_API_KEY:-} ]] && args+=(--perspective-api-key "$PERSPECTIVE_API_KEY")
[[ ${REDDIT_CLIENT_ID:-} ]] && args+=(--client-id "$REDDIT_CLIENT_ID")
[[ ${REDDIT_CLIENT_SECRET:-} ]] && args+=(--client-secret "$REDDIT_CLIENT_SECRET")
[[ ${REDDIT_USER_AGENT:-} ]] && args+=(--user-agent "$REDDIT_USER_AGENT")

export GITHUB_SEARCH_API_RATE_LIMIT=25

exec python3 "$SCANNER" "${args[@]}" "$@"
