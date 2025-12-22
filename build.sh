#!/usr/bin/env bash
# shellcheck enable=all shell=bash source-path=SCRIPTDIR
set -euo pipefail
IFS=$'\n\t' LC_ALL=C

has(){ command -v -- "$1" &>/dev/null; }
msg(){ printf '%s\n' "$@"; }
die(){ printf '%s\n' "$1" >&2; exit "${2:-1}"; }

has makepkg || die "makepkg not found - install 'base-devel'"
has python || die "python not found"

if [[ -f PKGBUILD-local ]]; then
  msg 'Building local development package.. .'
  makepkg -f -p PKGBUILD-local "$@"
else
  msg 'Building release package...'
  makepkg -f "$@"
fi

msg $'\nBuilt packages:'
ls -lh . /*.pkg.tar.zst 2>/dev/null || msg 'No packages found'
