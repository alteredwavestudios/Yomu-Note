#!/usr/bin/env bash
# Make an AppImage from build-linux.sh's standalone bundle.
# Provide the appimagetool path (and optional runtime) on the command line.
# Linux distribution compatibility STILL needs a clean-machine smoke test.
set -euo pipefail
cd "$(dirname "$0")/.."
tool="${1:-appimagetool}"
runtime="${2:-}"
source="$PWD/dist/Yomu Note"
[[ -x "$source/Yomu Note" ]] || { echo "Missing executable: $source/Yomu Note" >&2; exit 1; }
appdir="$PWD/.build/YomuNote.AppDir"
rm -rf "$appdir"
mkdir -p "$appdir/usr/bin"
cp -a "$source" "$appdir/usr/bin/Yomu Note"
cp assets/icon.png "$appdir/yomu-note.png"
ln -s yomu-note.png "$appdir/.DirIcon"
cat > "$appdir/yomu-note.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Yomu Note
Comment=Offline reading, annotation and shared study notebooks
Exec=yomu-note
Icon=yomu-note
Terminal=false
Categories=Education;Office;
DESKTOP
cat > "$appdir/AppRun" <<'APPRUN'
#!/bin/sh
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$HERE/usr/bin/Yomu Note/Yomu Note" "$@"
APPRUN
chmod +x "$appdir/AppRun"
mkdir -p release-assets
arch="$(uname -m)"
output="$PWD/release-assets/YomuNote-0.8.1b-Linux-${arch}.AppImage"
args=()
if [[ -n "$runtime" ]]; then args+=(--runtime-file "$runtime"); fi
ARCH="$arch" APPIMAGE_EXTRACT_AND_RUN=1 "$tool" "${args[@]}" "$appdir" "$output"
test -s "$output"
echo "AppImage generated at $output"
