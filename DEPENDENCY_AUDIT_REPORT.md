# Dependency Audit Report

**Date:** 2025-12-26
**Project:** account-scanner (moderation-scanner)
**Version:** 1.2.3

## Executive Summary

This audit analyzed all Python dependencies and GitHub Actions for security vulnerabilities, outdated packages, and unnecessary bloat. **Critical security vulnerabilities were found** in build tools that require immediate attention.

## 🔴 Critical Issues

### Security Vulnerabilities (7 found)

#### 1. cryptography (4 vulnerabilities)
- **Current Version:** 41.0.7
- **Recommended Version:** 46.0.3+
- **Vulnerabilities:**
  - **PYSEC-2024-225**: NULL pointer dereference in PKCS12 serialization (Fix: 42.0.4+)
  - **CVE-2023-50782**: RSA key exchange vulnerability allowing message decryption (Fix: 42.0.0+)
  - **CVE-2024-0727**: PKCS12 format DoS vulnerability (Fix: 42.0.2+)
  - **GHSA-h4gh-qq45-vh27**: OpenSSL vulnerability in bundled wheels (Fix: 43.0.1+)

#### 2. pip (1 vulnerability)
- **Current Version:** 24.0
- **Recommended Version:** 25.3
- **Vulnerability:**
  - **CVE-2025-8869**: Path traversal in tar archive extraction (Fix: 25.3)
  - **Note:** Python 3.11.14 implements PEP 706, which mitigates this issue

#### 3. setuptools (2 vulnerabilities)
- **Current Version:** 68.1.2
- **Recommended Version:** 80.9.0
- **Vulnerabilities:**
  - **PYSEC-2025-49**: Path traversal in PackageIndex → RCE potential (Fix: 78.1.1+)
  - **CVE-2024-6345**: Code injection via package_index module (Fix: 70.0.0+)

## 🟡 Outdated Dependencies

### Build System Dependencies
These are outdated but not directly specified in pyproject.toml:
- **setuptools**: 68.1.2 → 80.9.0 (18 months behind)

### Core Dependencies (pyproject.toml)
All core dependencies are **UP TO DATE**:
- ✅ httpx: 0.28.1 (latest: 0.28.1)
- ✅ orjson: 3.11.5 (latest: 3.11.5)
- ✅ asyncpraw: 7.8.1 (latest: 7.8.1)
- ✅ uvloop: 0.22.1 (latest in 0.22.x range)
- ✅ aiofiles: 24.1.0 (latest in 24.x range)
- ✅ py-cord: 2.7.0 (latest: 2.7.0)

### GitHub Actions
All GitHub Actions are **UP TO DATE**:
- ✅ actions/checkout: v6 (latest)
- ✅ actions/setup-python: v6 (latest)
- ✅ actions/upload-artifact: v6 (latest)
- ✅ actions/download-artifact: v7 (latest)
- ✅ actions/dependency-review-action: v4 (latest)

## 🟢 Dependency Analysis

### Transitive Dependencies (installed but not declared)
These are pulled in by declared dependencies:
- **aiohttp** (3.13.2): Required by asyncpraw, asyncprawcore, py-cord
- **httpcore** (1.0.9): Required by httpx
- **update-checker** (0.18.0): Required by asyncpraw
- **aiosqlite** (0.17.0): Required by asyncpraw
- **asyncprawcore** (2.4.0): Required by asyncpraw

**Assessment**: All transitive dependencies are legitimate and necessary.

### Potential Bloat
- **aiohttp + httpx duplication**: The project uses `httpx` for HTTP/2 support, but `asyncpraw` and `py-cord` depend on `aiohttp`. This is unavoidable without forking those libraries.
- **aiosqlite**: Used by asyncpraw for caching, not directly used by the project but necessary for optimal Reddit API performance.

## 📋 Issues Found in Configuration

### Fixed During Audit
✅ **Duplicate pytest.ini_options** in pyproject.toml (lines 93-101)
  - **Impact**: Build system errors preventing pip installation
  - **Status**: FIXED - Merged duplicate sections

## 🎯 Recommendations

### Priority 1: Immediate Action Required

#### 1. Update Build System (CRITICAL - Security)
```bash
pip install --upgrade pip setuptools wheel
```
**Why:** Fixes RCE and path traversal vulnerabilities in setuptools.

#### 2. Pin Minimum Build System Versions in pyproject.toml
**Current:**
```toml
[build-system]
requires = ["setuptools>=68.0"]
```

**Recommended:**
```toml
[build-system]
requires = ["setuptools>=78.1.1"]
build-backend = "setuptools.build_meta"
```

#### 3. Add Package Discovery Configuration
The project has a non-standard structure (Python files in root). Add to pyproject.toml:
```toml
[tool.setuptools]
py-modules = ["account_scanner", "discord_bot"]
```

### Priority 2: Security Best Practices

#### 1. Add Security Scanning to CI/CD
The project has `dependency-review.yml` but should add automated security scanning:

Create `.github/workflows/security-scan.yml`:
```yaml
name: Security Scan

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pip-audit
      - name: Run pip-audit
        run: pip-audit --desc
```

#### 2. Pin Exact Versions for Production
While ranges are good for library development, consider pinning for deployment:
- Add a `requirements-lock.txt` generated with `pip freeze`
- Update via Dependabot or Renovate

#### 3. Enable Dependabot
Create `.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Priority 3: Dependency Hygiene

#### 1. Update Version Constraints
Consider broadening version constraints to allow patch updates:

**Current:**
```toml
dependencies = [
  "httpx[http2]>=0.28.0,<0.29.0",
  "uvloop>=0.22.0,<0.23.0; platform_system != 'Windows'",
  "aiofiles>=24.1.0,<25.0.0",
]
```

**Recommended (allow minor updates):**
```toml
dependencies = [
  "httpx[http2]~=0.28.0",     # Allows 0.28.x
  "uvloop~=0.22.0; platform_system != 'Windows'",
  "aiofiles~=24.1",           # Allows 24.x
  # Keep tight constraints on API-breaking libraries:
  "orjson>=3.11.0,<4.0.0",
  "asyncpraw>=7.8.0,<8.0.0",
  "py-cord>=2.6.0,<3.0.0",
]
```

#### 2. Add Development Tools Version Pins
The dev dependencies have loose constraints. Consider:
```toml
[project.optional-dependencies]
dev = [
  "ruff~=0.8.0",           # Instead of >=0.8.0,<0.9.0
  "mypy~=1.14.0",
  "pytest~=8.3.0",
  "pytest-asyncio~=0.24.0",
  "pip-audit>=2.10.0",     # ADD: Security scanning
]
```

#### 3. Document External Dependencies
The project depends on the external `sherlock` CLI tool. Document in README:
- Installation instructions
- Version compatibility
- Fallback behavior

### Priority 4: Code Quality

#### 1. Add Type Stub Packages
For better type checking, add to dev dependencies:
```toml
dev = [
  # ... existing ...
  "types-aiofiles>=24.0.0",
]
```

#### 2. Remove Unused GitHub Actions Configuration
The `pylint.yml` workflow installs `pylint` but it's not in pyproject.toml dev dependencies. Either:
- Remove the workflow if not using pylint, OR
- Add `pylint` to dev dependencies

## 🔍 Dependency Breakdown

### Production Dependencies (6 packages → 23 total with transitive)
```
httpx[http2] (0.28.1)
├── httpcore (1.0.9)
├── h11 (0.16.0)
├── h2 (4.3.0)
│   ├── hpack (4.1.0)
│   └── hyperframe (6.1.0)
└── anyio (4.12.0)

orjson (3.11.5)

asyncpraw (7.8.1)
├── aiohttp (3.13.2)
├── aiosqlite (0.17.0)
├── asyncprawcore (2.4.0)
└── update-checker (0.18.0)

uvloop (0.22.1)

aiofiles (24.1.0)

py-cord (2.7.0)
└── aiohttp (3.13.2)
```

### Development Dependencies (4 packages)
```
ruff (linting + formatting)
mypy (type checking)
pytest (testing)
pytest-asyncio (async testing)
```

## 📊 Metrics

- **Total vulnerabilities found:** 7 (3 packages affected)
- **Critical vulnerabilities:** 2 (setuptools RCE, cryptography RSA)
- **Outdated core dependencies:** 0
- **Outdated transitive dependencies:** 3 (cryptography, pip, setuptools)
- **Unnecessary dependencies:** 0
- **Total dependency count:** ~23 packages (production)
- **Dependency freshness:** 100% for declared dependencies

## ✅ What's Working Well

1. **Minimal dependency footprint** - Only 6 direct dependencies
2. **Modern async stack** - uvloop, httpx with HTTP/2, asyncpraw
3. **Up-to-date core dependencies** - All declared packages are current
4. **GitHub Actions are current** - All actions using latest major versions
5. **Good CI/CD coverage** - Linting, type checking, testing all configured
6. **Security tooling present** - dependency-review-action configured

## 🔧 Implementation Checklist

- [ ] Update pip and setuptools: `pip install --upgrade pip setuptools`
- [ ] Update pyproject.toml build-system requirements to `setuptools>=78.1.1`
- [ ] Add `[tool.setuptools]` configuration for package discovery
- [ ] Create `.github/workflows/security-scan.yml` for automated scanning
- [ ] Create `.github/dependabot.yml` for automated updates
- [ ] Add pip-audit to dev dependencies
- [ ] Review and update version constraints using `~=` operator
- [ ] Document sherlock CLI dependency in README
- [ ] Verify pylint workflow or remove it

## 📚 Additional Resources

- [Python Packaging Security Guide](https://packaging.python.org/guides/security/)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)
- [Dependabot Configuration](https://docs.github.com/en/code-security/dependabot)
- [PEP 706: Filter for tarfile.extractall](https://peps.python.org/pep-0706/)
- [Semantic Versioning](https://semver.org/)

---

**Audit completed by:** Claude (Anthropic)
**Next review recommended:** 2026-03-26 (3 months)
