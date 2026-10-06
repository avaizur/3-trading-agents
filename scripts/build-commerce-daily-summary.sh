#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PACKAGE_DIR="${PROJECT_ROOT}/build/commerce-daily-summary-package"
ZIP_FILE="${PROJECT_ROOT}/build/commerce-daily-summary.zip"

echo "Building Commerce Daily Summary Lambda..."

rm -rf "${PACKAGE_DIR}"
rm -f "${ZIP_FILE}"

mkdir -p "${PACKAGE_DIR}"

cp "${PROJECT_ROOT}/src/lambda/commerce_daily_summary/handler.py" \
   "${PACKAGE_DIR}/handler.py"

cd "${PACKAGE_DIR}"

zip -qr "${ZIP_FILE}" .

echo
echo "Created:"
ls -lh "${ZIP_FILE}"
