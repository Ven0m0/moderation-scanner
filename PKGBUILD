# Maintainer: Ven0m0
pkgname=account-scanner
pkgver=1.2.3
pkgrel=1
pkgdesc="Multi-source account scanner: Reddit toxicity + Sherlock OSINT"
arch=(any)
url="https://github.com/Ven0m0/moderation-scanner"
license=(MIT)
depends=(
  python
  python-httpx
  python-orjson
  python-asyncpraw
  python-aiofiles
)
makedepends=(
  python-build
  python-installer
  python-wheel
  python-setuptools
)
optdepends=(
  'python-uvloop: async event loop performance boost (Linux only)'
  'sherlock-git: Hunt down social media accounts by username across social networks'
  'python-ruff: code formatting and linting'
  'python-mypy: static type checking'
  'python-pytest: running test suite'
  'python-pytest-asyncio: async test support'
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
  python -m build --wheel --no-isolation
}

check() {
  cd "$pkgname"
  PYTHONPATH="$PWD" pytest -v || :
}

package() {
  cd "${pkgname}-${pkgver}"
  python -m installer --destdir="${pkgdir}" dist/*.whl
  # Install wrapper script
  install -Dm755 scan.sh "${pkgdir}/usr/bin/${pkgname}-wrapper"
  # Install documentation
  install -Dm644 README.md "${pkgdir}/usr/share/doc/${pkgname}/README.md"
  install -Dm644 CHANGELOG.md "${pkgdir}/usr/share/doc/${pkgname}/CHANGELOG.md"
  # Install credential template
  install -Dm644 credentials.template "${pkgdir}/usr/share/doc/${pkgname}/credentials.template"
  # Install license
  install -Dm644 LICENSE "${pkgdir}/usr/share/licenses/${pkgname}/LICENSE"
}
