# OBJ UV Packer

Takes Wavefront OBJ models with multiple textures and packs them into a single texture atlas, rewriting UV coordinates to match. Available as both a command-line tool and a GUI application.

## Quick Start

1. **[Download the latest release](https://github.com/Zetaphor/imagepacker/releases/latest)** (Windows or Linux)
2. Extract the zip and run **OBJ UV Packer**
3. Click **Open OBJ File** (single model) or **Open Folder** (batch process a directory)
4. Click **Pack Textures**
5. Find your packed model in the `_packed` folder next to the original

## Why?

Originally put together for packing complex models with multiple textures into a single `.obj` + texture file for use as custom models in [Tabletop Simulator](http://berserk-games.com/tabletop-simulator/). Instead of manually combining textures in GIMP and repositioning UVs in Blender, this tool automates the entire process.

It analyses what texture files a model uses and how much of each texture is referenced by UV coordinates. It optionally crops textures down to just the used region before bin-packing them into a single atlas. Finally, it outputs a new `.obj` with updated UV coordinates, an updated `.mtl`, and the packed texture.

## Installation

### GUI Application (no Python required)

Download a pre-built binary from the [latest release](https://github.com/Zetaphor/imagepacker/releases/latest):

- **Windows**: `OBJ-UV-Packer-Windows.zip`
- **Linux**: `OBJ-UV-Packer-Linux.zip`

Extract the zip and run the executable. No Python installation needed.

### From source

Requires [Python 3.13+](https://www.python.org/downloads/) and [Pillow](https://python-pillow.github.io/):

```bash
pip install pillow
```

## Usage

### GUI Application

Launch the GUI by running `python gui.py` (from source) or double-clicking the built executable.

**Single file mode:**
1. Click **"Open OBJ File..."** and select your `.obj` file
2. The MTL is auto-detected from the OBJ's `mtllib` directive. Use the MTL override to select a different one if needed.
3. Adjust options (crop, tile, wrap) as desired
4. Click **"Pack Textures"**
5. Output is written to a `_packed` subfolder next to the original `.obj`

**Batch folder mode:**
1. Click **"Open Folder..."** and select a directory containing model subfolders
2. The tool recursively discovers all `.obj` files (skipping any `_packed` output directories)
3. Each model is packed sequentially with auto-detected MTL files
4. A summary shows which models succeeded or failed

### Command Line

```bash
python objuvpacker.py path/to/model.obj
```

The CLI wraps the same packing engine with terminal-based prompts.

#### Arguments

| Argument | Description |
|---|---|
| `obj` | Path to the `.obj` file (required) |
| `-m, --material` | Explicitly specify the `.mtl` file |
| `-o, --output` | Output name (used for folder and files) |
| `-a, --add` | Additional images to pack |
| `--no-crop` | Disable cropping and tiling |
| `--no-tile` | Don't prompt to tile/unroll wrapped textures |
| `--no-wrap` | Don't shift UV verts into [0,1] space |

#### Troubleshooting

If you're having trouble packing a model, try `--no-crop` and `--no-wrap` for the simplest possible packing.

### Texture file requirements

The textures referenced in the `.mtl` must be accessible. The tool:

1. Extracts the filename from the path in the MTL (handles Windows-style absolute paths on Linux)
2. Looks for the file locally next to the `.obj` first
3. Falls back to the full path as written in the MTL

Supported image formats: anything Pillow supports (`.png`, `.jpg`, `.tga`, `.bmp`, etc.)

### Tiling / wrapping warnings

When a texture has UV coordinates outside the normal `[0,1]` range, the tool will prompt you (dialog in GUI, text prompt in CLI):

> The texture 'track_segment.tga' has UV coordinates that imply it tiles 1.0x10.7 times.
> Do you want to tile this texture?

This happens when:

1. **Intentional tiling** (e.g. tank track segments that repeat) -- answer **Yes** to unroll
2. **Unused UV islands** placed outside normal space -- answer **No** (safe to ignore)
3. **Bugs or coordinate system differences** -- answer **No**, then check the result

Since the packer combines textures into one atlas, each texture no longer tiles infinitely. Models that rely on wrapping need to be "unrolled" by tiling the texture to cover the full UV extent.

## Building from source

### Prerequisites

```bash
pip install pillow pyinstaller
```

### Linux

```bash
./build.sh
```

Produces `dist/OBJ UV Packer` (standalone ELF binary).

### Automated releases

A GitHub Actions workflow automatically builds both Windows and Linux binaries on every push to `master` and publishes them as a [GitHub release](https://github.com/Zetaphor/imagepacker/releases). You can also trigger a build manually from the Actions tab.

### Windows (manual build)

To build manually on Windows:

```bat
pip install pillow pyinstaller
pyinstaller --onefile --windowed --name "OBJ UV Packer" gui.py
```

## Project structure

```
.
├── gui.py                  # tkinter GUI application
├── objuvpacker.py          # CLI wrapper
├── packer.py               # Core packing logic (callback-based API)
├── imagepacker/
│   ├── __init__.py
│   └── imagepacker.py      # Bin-packing algorithm and image operations
├── build.sh                # Linux build script
├── .github/
│   └── workflows/
│       └── build.yml       # GitHub Actions Windows build
└── pyproject.toml
```

## Technical details

A simple rectangle bin-packing algorithm places cropped textures into a single atlas. The algorithm is not optimal and is partly vertically biased. It does not attempt to rotate rectangles, but whitespace compresses well in practice.

## License

MIT License -- see [LICENSE](LICENSE) for details.
