#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PACKAGE_DIR="${PROJECT_ROOT}/build/commerce-order-monitor-package"
ZIP_FILE="${PROJECT_ROOT}/build/commerce-order-monitor.zip"

echo "Building Commerce Order Monitor Lambda..."

rm -rf "${PACKAGE_DIR}"
rm -f "${ZIP_FILE}"

mkdir -p "${PACKAGE_DIR}"

"${PROJECT_ROOT}/.venv/bin/pip" install \
  --quiet \
  --disable-pip-version-check \
  "pydantic>=2.8,<3" \
  --target "${PACKAGE_DIR}"

cp "${PROJECT_ROOT}/src/lambda/commerce_order_monitor/handler.py" \
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
