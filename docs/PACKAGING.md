# Packaging Guide

## Overview

This project includes complete Arch Linux packaging support for both release and development installations.

## Files

### PKGBUILD Files

| File | Purpose | Source |
|------|---------|--------|
| `config/PKGBUILD` | Release package | Downloads from GitHub tag |

### Build Scripts

| File | Purpose |
|------|---------|
| `scripts/build.sh` | Build helper script |
| `Makefile` | Build automation (see `make pkg`) |

## Building Packages

### Development Package (Local)

Builds from your current working directory with all local changes:

```bash
# Build only
make pkg

# Build and install
make pkg-install

# Or manually
./scripts/build.sh
sudo pacman -U account-scanner-git-*.pkg.tar.zst
```

**Package name:** `account-scanner-git`
**Version:** Based on git commits (e.g., `r42.a1b2c3d`)

### Release Package (Official)

Builds from a GitHub release tag:

```bash
# Edit PKGBUILD to update pkgver and checksums
makepkg -f

# Install
sudo pacman -U account-scanner-*.pkg.tar.zst
```

**Package name:** `account-scanner`
**Version:** Fixed version from PKGBUILD (e.g., `1.2.3`)

## Package Contents

After installation (`/usr/`):

```
/usr/
├── bin/
│   └── account-scanner-wrapper          # Bash wrapper script
├── lib/python3.*/site-packages/
│   └── account_scanner.py               # Main Python module
└── share/
    ├── doc/account-scanner/
    │   ├── README.md
    │   ├── CHANGELOG.md
    │   └── credentials.template
    └── licenses/account-scanner/
        └── LICENSE
```

## Using Installed Package

### Via Entry Point
```bash
# Installed by setuptools
account-scanner --help
account-scanner username --mode sherlock
```

### Via Wrapper Script
```bash
# Loads credentials from ~/.config/account_scanner/credentials
account-scanner-wrapper username --mode both
```

### As Python Module
```bash
python -m account_scanner username --mode reddit
```

## Dependencies

### Build-time (makedepends)
- `python-build`
- `python-installer`
- `python-wheel`
- `python-setuptools`

### Runtime (depends)
- `python` (≥3.11)
- `python-httpx`
- `python-orjson`
- `python-asyncpraw`
- `python-aiofiles`

### Optional (optdepends)
- `python-uvloop` - Performance boost (Linux only)
- `sherlock-project` - OSINT functionality
- `python-ruff` - Development: linting
- `python-mypy` - Development: type checking
- `python-pytest` - Development: testing
- `python-pytest-asyncio` - Development: async tests

## Updating Version

### For Release (config/PKGBUILD)

1. **Update version:**
   ```bash
   # In config/PKGBUILD
   pkgver=1.2.4
   pkgrel=1
   ```

2. **Update source URL:**
   ```bash
   source=("$pkgname-$pkgver.tar.gz::https://github.com/Ven0m0/$pkgname/archive/v$pkgver.tar.gz")
   ```

3. **Update checksums:**
   ```bash
   updpkgsums
   # Or manually: sha256sum downloaded-file.tar.gz
   ```

4. **Test build:**
   ```bash
   makepkg -f
   ```

## AUR Submission

### Initial Submission

1. **Create AUR package:**
   ```bash
   # Ensure PKGBUILD and .SRCINFO are up to date
   makepkg --printsrcinfo > .SRCINFO
   
   # Create git repository
   git clone ssh://aur@aur.archlinux.org/account-scanner.git aur-account-scanner
   cd aur-account-scanner
   
   # Copy packaging files
   cp ../PKGBUILD ../.SRCINFO .
   
   # Commit and push
   git add PKGBUILD .SRCINFO
   git commit -m "Initial commit: account-scanner 1.2.3"
   git push origin master
   ```

### Updates

1. **Update PKGBUILD:**
   ```bash
   # Bump version
   pkgver=1.2.4
   pkgrel=1
   
   # Update checksums
   updpkgsums
   
   # Regenerate .SRCINFO
   makepkg --printsrcinfo > .SRCINFO
   ```

2. **Test build:**
   ```bash
   makepkg -f
   sudo pacman -U account-scanner-*.pkg.tar.zst
   ```

3. **Push to AUR:**
   ```bash
   git commit -am "Update to 1.2.4"
   git push
   ```

## Makefile Targets

```bash
make pkg          # Build local development package
make pkg-install  # Build and install local package
make pkg-clean    # Remove package artifacts
```

## Troubleshooting

### Build Fails - Missing Dependencies
```bash
# Install build dependencies
sudo pacman -S python-build python-installer python-wheel python-setuptools
```

### Tests Fail During check()
Tests are non-critical for package building. They run with `|| true` to prevent build failure.

### Version Mismatch
Ensure `pyproject.toml` and `config/PKGBUILD` have matching versions:
```bash
grep "version = " pyproject.toml
grep "pkgver=" config/PKGBUILD
```

### .SRCINFO Out of Sync
```bash
makepkg --printsrcinfo > .SRCINFO
git diff .SRCINFO  # Review changes
```

## Clean Builds

```bash
# Remove all package artifacts
make pkg-clean

# Full clean including Python artifacts
make clean pkg-clean

# Nuclear option - git clean
git clean -fdx
```

## Advanced Usage

### Custom Build Flags
```bash
# Skip tests
makepkg -f --nocheck

# Install directly
makepkg -si

# Clean build
makepkg -C -f
```

### Split Packages
Future enhancement - could split into:
- `account-scanner` - Core package
- `account-scanner-dev` - Development tools
- `account-scanner-sherlock` - Sherlock integration

## Best Practices

1. **Always test locally** before AUR push
2. **Use `updpkgsums`** instead of manual hash updates
3. **Version bump `pkgrel`** for packaging fixes (same upstream version)
4. **Reset `pkgrel=1`** when bumping `pkgver`
5. **Test installation** in clean chroot before release

## References

- [Arch Package Guidelines](https://wiki.archlinux.org/title/PKGBUILD)
- [Python Package Guidelines](https://wiki.archlinux.org/title/Python_package_guidelines)
- [AUR Submission Guidelines](https://wiki.archlinux.org/title/AUR_submission_guidelines)
- [makepkg Manual](https://man.archlinux.org/man/makepkg.8)
