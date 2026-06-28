#!/bin/bash
# Build ClamProtect AppImage
set -euo pipefail

APP="ClamProtect"
VERSION="1.0.1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
APPDIR="${SCRIPT_DIR}/AppDir"

echo "==> Cleaning old AppDir"
rm -rf "${APPDIR}/usr/share/clamprotect" "${APPDIR}/usr/bin/clamprotect"

echo "==> Copying application source"
mkdir -p "${APPDIR}/usr/share/clamprotect"
cp -r "${PROJECT_DIR}/main.py" "${APPDIR}/usr/share/clamprotect/"
cp -r "${PROJECT_DIR}/core"    "${APPDIR}/usr/share/clamprotect/"
cp -r "${PROJECT_DIR}/ui"      "${APPDIR}/usr/share/clamprotect/"
cp -r "${PROJECT_DIR}/watcher" "${APPDIR}/usr/share/clamprotect/"
cp -r "${PROJECT_DIR}/resources" "${APPDIR}/usr/share/clamprotect/resources"
# Create an initialization hook to ensure Python binds the split layout namespace
cat > "${APPDIR}/usr/share/clamprotect/__init__.py" << 'INIT'
import sys
try:
    import PyQt6
    import PyQt6.sip
    sys.modules['PyQt6.sip'] = PyQt6.sip
except ImportError:
    pass
INIT


echo "==> Installing desktop file and icon"
cp "${PROJECT_DIR}/resources/clamprotect.desktop" "${APPDIR}/clamprotect.desktop"
cp "${PROJECT_DIR}/resources/icons/clamprotect.svg" "${APPDIR}/clamprotect.svg"

mkdir -p "${APPDIR}/usr/share/applications" "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
cp "${PROJECT_DIR}/resources/clamprotect.desktop" "${APPDIR}/usr/share/applications/"
cp "${PROJECT_DIR}/resources/icons/clamprotect.svg" "${APPDIR}/usr/share/icons/hicolor/scalable/apps/"
cp "${APPDIR}/usr/share/icons/hicolor/scalable/apps/clamprotect.svg" "${APPDIR}/.DirIcon"

echo "==> Creating launcher symlinks"
ln -sf "../share/clamprotect/main.py" "${APPDIR}/usr/bin/clamprotect"
ln -sf "../share/clamprotect/resources/clamprotect-scan" "${APPDIR}/usr/bin/clamprotect-scan"

echo "==> Installing AppStream metadata"
mkdir -p "${APPDIR}/usr/share/metainfo"
cat > "${APPDIR}/usr/share/metainfo/com.github.clamprotect.clamprotect.appdata.xml" << 'APPSTREAM'
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>com.github.clamprotect.clamprotect</id>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <name>ClamProtect</name>
  <summary>Modern ClamAV GUI — Real-time malware protection</summary>
  <developer id="team.clamprotect">
    <name>ClamProtect Team</name>
  </developer>
  <description>
    <p>ClamProtect brings a modern graphical interface to ClamAV. It offers on-demand scanning, real-time file monitoring, scheduled scans, quarantine management, and system tray integration.</p>
  </description>
  <url type="homepage">https://github.com/clamprotect/clamprotect</url>
  <launchable type="desktop-id">clamprotect.desktop</launchable>
  <categories>
    <category>Utility</category>
    <category>Security</category>
  </categories>
  <releases>
    <release version="1.0.1" date="2026-06-28"/>
    <release version="1.0.0" date="2026-06-26"/>
  </releases>
</component>
APPSTREAM

echo "==> Bundling PyQt6 with pip"
python3 -m pip install --target="${APPDIR}/usr/share/clamprotect/pylibs" \
    --force-reinstall --no-cache-dir \
    PyQt6 PyQt6-Qt6 PyQt6-sip

cat > "${APPDIR}/usr/bin/python3-launcher" << 'PYTHON'
#!/bin/bash
BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
HERE="$(cd "${BIN_DIR}/../share/clamprotect" && pwd)"

BUNDLE_LIBS="${HERE}/pylibs/PyQt6/Qt6/lib"

export PYTHONPATH="${HERE}/pylibs:${HERE}:${PYTHONPATH:-}"
export QT_PLUGIN_PATH="${HERE}/pylibs/PyQt6/Qt6/plugins:${QT_PLUGIN_PATH:-}"
export LD_LIBRARY_PATH="${BUNDLE_LIBS}:${LD_LIBRARY_PATH:-}"

exec python3 "$@"
PYTHON
chmod +x "${APPDIR}/usr/bin/python3-launcher"

cat > "${APPDIR}/AppRun" << 'RUN'
#!/bin/bash
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "${HERE}/usr/bin/python3-launcher" "${HERE}/usr/share/clamprotect/main.py" "$@"
RUN
chmod +x "${APPDIR}/AppRun"

echo "==> AppDir ready at: ${APPDIR}"
echo ""
echo "To create the AppImage:"
echo ""
echo "  1. Download appimagetool:"
echo "     wget -O appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
echo "     chmod +x appimagetool"
echo ""
echo "  2. Download runtime (if appimagetool fails with 302):"
echo '     wget -O runtime-x86_64 https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64'
echo ""
echo "  3. Build:"
echo "     ARCH=x86_64 ./appimagetool --runtime-file runtime-x86_64 ${APPDIR} ${APP}-${VERSION}-x86_64.AppImage"
echo ""


