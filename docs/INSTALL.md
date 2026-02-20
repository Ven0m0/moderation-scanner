# Installation Guide

## Quick Reference

| Method | Best For | Command |
|--------|----------|---------|
| Pip editable | Development | `pip install -e .` |
| Pip wheel | Production | `pip install .` |
| Arch package | System-wide | `make pkg-install` |
| AUR | Arch users | `yay -S account-scanner` |

## Method 1: Pip (Development)

**Best for:** Active development, testing changes

```bash
# Clone repository
git clone https://github.com/Ven0m0/moderation-scanner
cd moderation-scanner

# Install in editable mode
pip install -e .

# Install dev dependencies
pip install -e ".[dev]"
```

**Advantages:**
- Changes reflect immediately
- Easy to edit code
- Can run tests

**Disadvantages:**
- Not system-wide
- Requires virtualenv for isolation

## Method 2: Pip (Production)

**Best for:** Production deployments, Docker containers

```bash
# Install from wheel
pip install .

# Or from PyPI (when published)
pip install account-scanner
```

**Advantages:**
- Clean installation
- Faster startup
- No editable artifacts

## Method 3: Arch Package (Local Build)

**Best for:** Arch Linux system-wide installation

```bash
# Build package from current directory
make pkg

# Build and install in one step
make pkg-install

# Or manually
./scripts/build.sh
sudo pacman -U account-scanner-git-*.pkg.tar.zst
```

**Advantages:**
- Managed by pacman
- System-wide installation
- Automatic dependency resolution
- Clean uninstallation

**Post-install:**
```bash
# Wrapper script
account-scanner-wrapper --help

# Python module
account-scanner --help

# Documentation
cat /usr/share/doc/account-scanner-git/README.md
```

**Uninstall:**
```bash
sudo pacman -R account-scanner-git
```

## Method 4: AUR (Official Repository)

**Best for:** Arch users wanting automatic updates

```bash
# Using yay
yay -S account-scanner

# Using paru
paru -S account-scanner

# Manually
git clone https://aur.archlinux.org/account-scanner.git
cd account-scanner
makepkg -si
```

**Advantages:**
- Automatic updates with system
- Verified by AUR moderators
- Community support

## Dependency Management

### Core Dependencies
- `python >= 3.11`
- `python-httpx[http2]`
- `python-orjson`
- `python-asyncpraw`
- `python-aiofiles`

### Optional Dependencies
- `python-uvloop` - Async performance (Linux only)
- `sherlock-project` - OSINT scanning
- `python-ruff` - Linting/formatting
- `python-mypy` - Type checking
- `python-pytest` - Testing

### Installing Optional Deps

**Pip:**
```bash
pip install account-scanner[dev]
pip install sherlock-project
```

**Arch:**
```bash
sudo pacman -S python-uvloop python-ruff python-mypy python-pytest
yay -S sherlock-project
```

## Post-Installation Setup

### 1. Create Config Directory
```bash
mkdir -p ~/.config/account_scanner
```

### 2. Setup Credentials
```bash
# Copy template
cp /usr/share/doc/account-scanner/credentials.template \
   ~/.config/account_scanner/credentials

# Edit with your API keys
vim ~/.config/account_scanner/credentials
```

### 3. Verify Installation
```bash
# Check version
account-scanner --help

# Or with wrapper
account-scanner-wrapper --help

# Test Sherlock integration
account-scanner test_user --mode sherlock --verbose
```

## Upgrading

### Pip
```bash
pip install --upgrade account-scanner
```

### Arch Package
```bash
# Rebuild and reinstall
make pkg-install

# Or via AUR
yay -Syu account-scanner
```

## Troubleshooting

### Import Errors
```bash
# Verify installation
pip show account-scanner

# Check Python path
python -c "import account_scanner; print(account_scanner.__file__)"
```

### Missing Sherlock
```bash
# Install Sherlock
pip install sherlock-project

# Verify
which sherlock
sherlock --version
```

### Permission Issues (Arch)
```bash
# Check file ownership
ls -la /usr/bin/account-scanner*

# Reinstall if needed
sudo pacman -R account-scanner-git
make pkg-install
```

### uvloop Not Available (Windows)
This is expected - uvloop only works on Linux/macOS. The package will run fine without it, just with slightly lower async performance.

## Development Setup

For contributing or local development:

```bash
# Clone and setup
git clone https://github.com/Ven0m0/moderation-scanner
cd moderation-scanner

# Install in editable mode with dev deps
make dev

# Run checks
make check

# Run tests
make test

# Build package
make pkg
```

## Uninstallation

### Pip
```bash
pip uninstall account-scanner
```

### Arch
```bash
sudo pacman -R account-scanner-git
# or
sudo pacman -R account-scanner
```

### Clean All Artifacts
```bash
# Python artifacts
make clean

# Package artifacts
make pkg-clean

# Config (careful!)
rm -rf ~/.config/account_scanner
```
