#!/usr/bin/env bash
# shellcheck enable=all shell=bash source-path=SCRIPTDIR
set -euo pipefail
IFS=$'\n\t' LC_ALL=C

err() { printf '%s\n' "$*" >&2; }
die() { err "$@"; exit 1; }

# Check dependencies
command -v makepkg &>/dev/null || die "makepkg not found - install 'base-devel'"
command -v python &>/dev/null || die "python not found"

# Build from local PKGBUILD
if [[ -f PKGBUILD-local ]]; then
  printf 'Building local development package...\n'
  makepkg -f -p PKGBUILD-local "$@"
else
  printf 'Building release package...\n'
  makepkg -f "$@"
fi

# Show built packages
printf '\nBuilt packages:\n'
ls -lh ./*.pkg.tar.zst 2>/dev/null || true
