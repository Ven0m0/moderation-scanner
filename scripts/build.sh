#!/usr/bin/env bash
# shellcheck enable=all shell=bash source-path=SCRIPTDIR
set -euo pipefail
IFS=$'\n\t' LC_ALL=C

has(){ command -v -- "$1" &>/dev/null; }
msg(){ printf '%s\n' "$@"; }
die(){ printf '%s\n' "$1" >&2; exit "${2:-1}"; }

has makepkg || die "makepkg not found - install 'base-devel'"
has python || die "python not found"

# Change to repository root
SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR/.."

if [[ -f config/PKGBUILD-local ]]; then
  msg 'Building local development package...'
  makepkg -f -p config/PKGBUILD-local "$@"
else
  msg 'Building release package...'
  makepkg -f -p config/PKGBUILD "$@"
fi

msg $'\nBuilt packages:'
ls -lh ./*.pkg.tar.zst 2>/dev/null || msg 'No packages found'
