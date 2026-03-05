#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="PicPlotterAuto"
DISPLAY_NAME="PicPlotter Auto"
DIST_DIR="${ROOT_DIR}/dist"
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
STAGING_DIR="${ROOT_DIR}/build_temp/dmg_root"

VERSION=""
if command -v python3 >/dev/null 2>&1; then
  VERSION="$(ROOT_DIR="${ROOT_DIR}" python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ.get("ROOT_DIR", ".")).resolve()
version = "0.0.0"
text = (root / "src" / "__init__.py").read_text(encoding="utf-8")
for line in text.splitlines():
    if line.strip().startswith("__version__"):
        version = line.split("=", 1)[1].strip().strip('"').strip("'")
        break
print(version)
PY
  )"
fi
if [ -z "${VERSION}" ]; then
  VERSION="$(grep -E "__version__" "${ROOT_DIR}/src/__init__.py" | sed -E 's/.*\"([^\"]+)\".*/\\1/')"
fi
if [ -z "${VERSION}" ]; then
  VERSION="0.0.0"
fi
VERSION="${VERSION%-auto}"

DMG_NAME="${APP_NAME}-${VERSION}.dmg"
DMG_PATH="${DIST_DIR}/${DMG_NAME}"

if [ ! -d "${APP_PATH}" ]; then
  echo "Missing app bundle: ${APP_PATH}"
  echo "Build on macOS first: python3 build/build.py"
  exit 1
fi

rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

cp -R "${APP_PATH}" "${STAGING_DIR}/${DISPLAY_NAME}.app"
ln -s /Applications "${STAGING_DIR}/Applications"

hdiutil create -volname "${DISPLAY_NAME}" -srcfolder "${STAGING_DIR}" -ov -format UDZO "${DMG_PATH}"

echo "DMG created: ${DMG_PATH}"
