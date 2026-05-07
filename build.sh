#!/usr/bin/env bash
set -euo pipefail

pip install pillow pyinstaller 2>/dev/null || pip install --user pillow pyinstaller

pyinstaller --onefile --windowed --name "OBJ UV Packer" gui.py

echo ""
echo "Build complete: dist/OBJ UV Packer"
