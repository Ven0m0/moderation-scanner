# Maintainer: Ven0m0
pkgname=account-scanner
pkgver=1.2.3
pkgrel=2
pkgdesc="Multi-source account scanner: Reddit toxicity + Sherlock OSINT with Discord bot integration"
arch=(any)
url="https://github.com/Ven0m0/moderation-scanner"
license=(MIT)
depends=(
  python>=3.11
  python-httpx
  python-orjson
  python-asyncpraw
  python-aiofiles
  python-discord.py
)
makedepends=(
  git
  python-build
  python-installer
  python-wheel
  python-setuptools
)
optdepends=(
  'python-uvloop: async event loop performance boost (Linux only)'
  'sherlock-git: Hunt down social media accounts by username across social networks'
  'python-ruff: code formatting and linting (development)'
  'python-mypy: static type checking (development)'
  'python-pytest: running test suite (development)'
  'python-pytest-asyncio: async test support (development)'
  'python-pytest-cov: test coverage reporting (development)'
  'python-pip-audit: dependency security auditing (development)'
  'python-bandit: code security analysis (development)'
)
source=("git+${url}.git")
sha256sums=('SKIP')
provides=(account-scanner)
conflicts=(account-scanner)

pkgver() {
  cd "$pkgname"
  printf "r%s.%s" "$(git rev-list --count HEAD)" "$(git rev-parse --short HEAD)"
}

build() {
  cd "$pkgname"
  export PYTHONOPTIMIZE=2
  export SETUPTOOLS_SCM_PRETEND_VERSION="${pkgver}"
  python -m build --wheel --no-isolation
}

check() {
  cd "$pkgname"
  msg2 "Running code quality checks..."

  # Format check
  if command -v ruff &>/dev/null; then
    msg2 "Checking code formatting with Ruff..."
    ruff format --check . || :
    ruff check . || :
  fi

  # Type check
  if command -v mypy &>/dev/null; then
    msg2 "Running type checks with mypy..."
    mypy account_scanner.py || :
  fi

  # Run tests
  msg2 "Running test suite..."
  PYTHONPATH="$PWD" pytest -v --tb=short || :
}

package() {
  cd "$pkgname"

  # Install Python package
  python -m installer --destdir="${pkgdir}" dist/*.whl

  # Install wrapper script
  install -Dm755 scan.sh "${pkgdir}/usr/bin/${pkgname}-wrapper"

  # Install documentation
  install -Dm644 README.md "${pkgdir}/usr/share/doc/${pkgname}/README.md"
  if [[ -f CHANGELOG.md ]]; then
    install -Dm644 CHANGELOG.md "${pkgdir}/usr/share/doc/${pkgname}/CHANGELOG.md"
  fi

  # Install credential template
  if [[ -f credentials.template ]]; then
    install -Dm644 credentials.template "${pkgdir}/usr/share/doc/${pkgname}/credentials.template"
  fi

  # Install license
  install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"

  # Install Makefile for development
  install -Dm644 Makefile "${pkgdir}/usr/share/doc/${pkgname}/Makefile"
}
