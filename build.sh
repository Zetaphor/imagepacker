#!/usr/bin/env bash
set -euo pipefail

pip install pillow tkinterdnd2 pyinstaller 2>/dev/null || pip install --user pillow tkinterdnd2 pyinstaller

pyinstaller --onefile --windowed \
    --collect-all tkinterdnd2 \
    --name "OBJ UV Packer" gui.py

echo ""
echo "Build complete: dist/OBJ UV Packer"
