#!/usr/bin/env bash
# shellcheck enable=all shell=bash source-path=SCRIPTDIR
set -euo pipefail; shopt -s nullglob globstar
IFS=$'\n\t' LC_ALL=C
# Paths
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCANNER="${SCRIPT_DIR}/account_scanner.py"
readonly CREDS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/account_scanner/credentials"
# Validation
err(){ printf '%s\n' "$*" >&2; }
die(){ err "$@"; exit 1; }
[[ -f $SCANNER ]] || die "Scanner not found: $SCANNER"
command -v python3 &>/dev/null || die "python3 not found in PATH"
# Load credentials (non-critical)
if [[ -f $CREDS_FILE ]]; then
  # shellcheck source=/dev/null
  source "$CREDS_FILE" || err "Warning: Failed to source $CREDS_FILE"
fi
# Build args from environment
args=()
[[ ${PERSPECTIVE_API_KEY:-} ]] && args+=(--perspective-api-key "$PERSPECTIVE_API_KEY")
[[ ${REDDIT_CLIENT_ID:-} ]] && args+=(--client-id "$REDDIT_CLIENT_ID")
[[ ${REDDIT_CLIENT_SECRET:-} ]] && args+=(--client-secret "$REDDIT_CLIENT_SECRET")
[[ ${REDDIT_USER_AGENT:-} ]] && args+=(--user-agent "$REDDIT_USER_AGENT")
# Execute
exec python3 "$SCANNER" "${args[@]}" "$@"
