#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PACKAGE_DIR="${PROJECT_ROOT}/build/commerce-watch-package"
ZIP_FILE="${PROJECT_ROOT}/build/commerce-watch.zip"

echo "Building Commerce Watch Lambda..."

rm -rf "${PACKAGE_DIR}"
rm -f "${ZIP_FILE}"

mkdir -p "${PACKAGE_DIR}"

python3 -m pip install \
  --quiet \
  --disable-pip-version-check \
  "pydantic>=2.8,<3" \
  --target "${PACKAGE_DIR}"

cp "${PROJECT_ROOT}/src/lambda/commerce_watch/handler.py" \
   "${PACKAGE_DIR}/handler.py"

mkdir -p "${PACKAGE_DIR}/src"

cp -R "${PROJECT_ROOT}/src/commerce" \
      "${PACKAGE_DIR}/src/commerce"

find "${PACKAGE_DIR}" \
  -type d \
  -name "__pycache__" \
  -prune \
  -exec rm -rf {} +

find "${PACKAGE_DIR}" \
  -type f \
  -name "*.pyc" \
  -delete

cd "${PACKAGE_DIR}"

zip -qr "${ZIP_FILE}" .

echo
echo "Created:"
ls -lh "${ZIP_FILE}"
