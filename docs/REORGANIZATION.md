# Repository Reorganization

This document explains the recent repository reorganization that improves maintainability and clarity.

## What Changed?

The repository has been reorganized from a flat structure to a more maintainable hierarchical structure:

### Before
```
moderation-scanner/
├── account_scanner.py
├── discord_bot.py
├── test-scanner.py
├── scan.sh
├── build.sh
├── run-bot.sh
├── PKGBUILD
├── discord-scanner-bot.service
├── README.md
├── INSTALL.md
├── CONTRIBUTING.md
├── PACKAGING.md
├── DEPLOYMENT.md
├── DISCORD_BOT_DEPLOYMENT.md
├── PRODUCTION.md
├── QUICKSTART.md
├── changelog.md
└── ... (other files)
```

### After
```
moderation-scanner/
├── account_scanner.py         # Core files remain in root
├── discord_bot.py
├── test-scanner.py
├── scripts/                   # ✨ NEW: Shell scripts
│   ├── scan.sh
│   ├── build.sh
│   └── run-bot.sh
├── config/                    # ✨ NEW: Configuration files
│   ├── PKGBUILD
│   └── discord-scanner-bot.service
├── docs/                      # ✨ NEW: Documentation hub
│   ├── README.md              # Documentation index
│   ├── INSTALL.md
│   ├── CONTRIBUTING.md
│   ├── PACKAGING.md
│   ├── changelog.md
│   └── deployment/            # ✨ NEW: Deployment docs
│       ├── DEPLOYMENT.md
│       ├── DISCORD_BOT_DEPLOYMENT.md
│       └── PRODUCTION.md
├── README.md                  # Kept in root for visibility
├── QUICKSTART.md              # Kept in root for easy access
└── ... (other files)
```

## Benefits

### 1. **Better Organization**
- All documentation in one place (`docs/`)
- Related deployment docs grouped together (`docs/deployment/`)
- Scripts separated from code (`scripts/`)
- Configuration files isolated (`config/`)

### 2. **Improved Discoverability**
- New `docs/README.md` provides a documentation index
- Clear separation of concerns
- Easier to find what you're looking for

### 3. **Cleaner Root Directory**
- Only essential files in root (README, LICENSE, QUICKSTART, core code)
- Reduced clutter from 15+ files to 8 key files
- Better first impression for new contributors

### 4. **Better Maintainability**
- Logical grouping makes updates easier
- Related files together reduce context switching
- Scalable structure for future growth

## Migration Guide

### For Users

No action needed! All functionality remains the same:

- **Scripts**: Use `./scripts/scan.sh` instead of `./scan.sh`
- **Makefile**: All make targets work the same (e.g., `make scan`, `make pkg`)
- **Documentation**: Check `docs/` directory or use the new [docs/README.md](docs/README.md) index

### For Contributors

Update any local references:

```bash
# Old paths
./scan.sh username
./build.sh
source CONTRIBUTING.md

# New paths
./scripts/scan.sh username
./scripts/build.sh
cat docs/CONTRIBUTING.md
```

### For Package Maintainers

The PKGBUILD has been updated with new paths:
- Location: `config/PKGBUILD` (was `PKGBUILD`)
- Wrapper script: `scripts/scan.sh` (was `scan.sh`)
- Changelog: `docs/changelog.md` (was `changelog.md`)

## Updated References

All references have been updated:

- ✅ README.md - Updated all documentation links
- ✅ QUICKSTART.md - Updated deployment guide links
- ✅ Makefile - Updated script paths
- ✅ Scripts - Updated to work from new locations
- ✅ PKGBUILD - Updated file paths
- ✅ GitHub workflows - Updated references

## Questions?

- See [docs/README.md](docs/README.md) for documentation index
- See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for development guide
- Open an issue for any problems

---

**Note**: This reorganization maintains backward compatibility. All URLs, APIs, and functionality remain unchanged.
