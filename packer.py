import os
from pprint import pformat
from imagepacker import pack_images


class AABB:
    def __init__(self, min_x=None, min_y=None, max_x=None, max_y=None):
        self.min_x = min_x
        self.min_y = min_y
        self.max_x = max_x
        self.max_y = max_y
        self.to_tile = False

    def add(self, x, y):
        self.min_x = min(self.min_x, x) if self.min_x is not None else x
        self.min_y = min(self.min_y, y) if self.min_y is not None else y
        self.max_x = max(self.max_x, x) if self.max_x is not None else x
        self.max_y = max(self.max_y, y) if self.max_y is not None else y

    def uv_wrap(self):
        return (self.max_x - self.min_x, self.max_y - self.min_y)

    def tiling(self):
        if self.min_x and self.max_x and self.min_y and self.max_y:
            if self.min_x < 0 or self.min_y < 0 or self.max_x > 1 or self.max_y > 1:
                return (self.max_x - self.min_x, self.max_y - self.min_y)
        return None

    def __repr__(self):
        return "({},{}) ({},{})".format(
            self.min_x, self.min_y, self.max_x, self.max_y
        )


class PackError(Exception):
    """Raised when packing cannot proceed."""


def guess_realpath(path):
    """Checks for a file in a path, or in a local path.
    Handles Windows-style absolute paths on Linux by extracting the basename.
    """
    basename = os.path.basename(path.replace("\\", "/"))

    if os.path.isfile(basename):
        return os.path.realpath(basename)
    elif os.path.isfile(path):
        return os.path.realpath(path)
    else:
        return None


def find_mtl(obj_lines, obj_dir):
    """Try to locate the .mtl file referenced in an .obj."""
    for line in obj_lines:
        if line.startswith("mtllib"):
            raw = line[7:]
            path = guess_realpath(os.path.join(obj_dir, os.path.basename(raw.replace("\\", "/"))))
            if path:
                return path
            path = guess_realpath(raw)
            if path:
                return path
    return None


def parse_mtl(mtl_path, output_name, log=None):
    """Parse an MTL file and return texture mapping info.

    Returns (texmap, names, dmaps, new_mtl_lines, missing_basenames).
    """
    if log is None:
        log = lambda msg: None

    mtl_lines = []
    with open(mtl_path, "r") as f:
        mtl_lines = [x.strip() for x in f.readlines()]

    if mtl_lines[0].strip() != "# Textures packed with a simple packer":
        mtl_lines.insert(0, "# Textures packed with a simple packer")

    names = []
    dmaps = []
    new_mtl_lines = []
    outname = output_name + "_full.png"
    all_material_names = set()
    missing_basenames = []

    for line in mtl_lines:
        if line.startswith("newmtl"):
            name = line[7:]
            if name and name != "None":
                if len(dmaps) != len(names):
                    names.pop()
                names.append(name)
                all_material_names.add(name)
            else:
                continue
        elif line.startswith("map_"):
            mtype, m = line.split(" ", 1)
            if mtype.lower() == "map_kd":
                dmap = guess_realpath(m)
                if not dmap:
                    bname = os.path.basename(m.replace("\\", "/"))
                    log("Missing texture file: " + bname)
                    missing_basenames.append(bname)
                dmaps.append(dmap)
                line = " ".join([mtype, outname])
            else:
                continue
        elif line.startswith("d "):
            continue

        new_mtl_lines.append(line)

    if len(dmaps) != len(names):
        names.pop()

    assert len(names) == len(dmaps)
    texmap = dict(zip(names, dmaps))

    for mat_name in all_material_names:
        if mat_name not in texmap:
            texmap[mat_name] = None

    return texmap, names, dmaps, new_mtl_lines, missing_basenames


def compute_extents(obj_lines, texmap, dmaps, log=None):
    """Walk OBJ faces to compute per-texture UV bounding boxes.

    Returns (textents dict, used_mtl set).
    """
    if log is None:
        log = lambda msg: None

    valid_dmaps = [d for d in set(dmaps) if d is not None]
    textents = {name: AABB() for name in valid_dmaps}

    uv_lines = []
    curr_mtl = None
    used_mtl = set()
    skipped_mtls = set()

    for line_idx, line in enumerate(obj_lines):
        if line.startswith("vt"):
            uv_lines.append(line_idx)
        elif line.startswith("usemtl"):
            curr_mtl = line[7:]
        elif line.startswith("f"):
            for vertex in line[2:].split():
                v_def = vertex.split(sep="/")
                if len(v_def) >= 2 and v_def[1]:
                    uv_idx = int(v_def[1]) - 1
                    uv_line_idx = uv_lines[uv_idx]
                    uv_line = obj_lines[uv_line_idx][3:]
                    uv = [float(u.strip()) for u in uv_line.split()]

                    if curr_mtl and curr_mtl in texmap:
                        tex_path = texmap[curr_mtl]
                        if tex_path is not None:
                            used_mtl.add(curr_mtl)
                            textents[tex_path].add(uv[0], uv[1])
                    elif curr_mtl and curr_mtl not in skipped_mtls:
                        log(curr_mtl + " not in texmap")
                        skipped_mtls.add(curr_mtl)

    return textents, used_mtl


def run_pack(obj_path, mtl_path=None, output_name=None, output_dir=None,
             crop=True, tile=True, wrap=True, additional=None,
             tile_callback=None, log_callback=None):
    """Main packing entry point.

    Args:
        obj_path: Path to the .obj file.
        mtl_path: Optional explicit path to .mtl file; auto-detected if None.
        output_name: Base name for output files; defaults to <obj_name>_packed.
        output_dir: Directory to write output into. If None, a subfolder named
            output_name is created next to the .obj file.
        crop: Crop textures to used UV region.
        tile: Offer to tile textures that extend outside UV space.
        wrap: Shift remaining UV verts into [0,1] space.
        additional: List of additional image paths to pack.
        tile_callback: callable(texture_name, h_tiles, v_tiles) -> bool.
            Called when a texture has tiling UVs. Return True to tile it.
            If None, tiling is always declined.
        log_callback: callable(message) for progress logging.
            If None, messages are discarded.

    Returns:
        Path to the output directory containing the packed files.

    Raises:
        PackError on recoverable problems (missing files, no textures, etc.).
        Other exceptions for unexpected failures.
    """
    log = log_callback if log_callback else lambda msg: None

    obj_path = os.path.realpath(obj_path)
    wdir = os.path.dirname(obj_path)
    original_dir = os.getcwd()

    try:
        os.chdir(wdir)

        obj_local_path = os.path.basename(obj_path)
        obj_name = os.path.splitext(obj_local_path)[0]

        if output_name is None:
            output_name = obj_name + "_packed"

        log("Reading OBJ file: " + obj_local_path)
        with open(obj_local_path, "r") as f:
            obj_lines = [x.strip() for x in f.readlines()]

        # Locate MTL
        if not mtl_path or not os.path.isfile(mtl_path):
            log("Auto-detecting MTL file...")
            mtl_path = find_mtl(obj_lines, wdir)
            if mtl_path:
                log("Found MTL: " + mtl_path)

        if not mtl_path or not os.path.isfile(mtl_path):
            raise PackError("Cannot find .mtl file! Provide it explicitly or "
                            "ensure it is referenced in the .obj and exists on disk.")

        log("Parsing material file...")
        texmap, names, dmaps, new_mtl_lines, missing_basenames = parse_mtl(
            mtl_path, output_name, log=log
        )

        log("\nMaterial -> texture map:\n" + pformat(texmap))

        # Compute UV extents
        textents = None
        if crop:
            log("Computing UV extents...")
            textents, used_mtl = compute_extents(obj_lines, texmap, dmaps, log=log)

            if tile:
                for name, extent in textents.items():
                    if extent.tiling():
                        h_w, v_w = extent.tiling()
                        if h_w > 1 or v_w > 1:
                            should_tile = False
                            if tile_callback:
                                should_tile = tile_callback(name, round(h_w, 1), round(v_w, 1))
                            extent.to_tile = should_tile
                            if should_tile:
                                log("Marking texture to be tiled: " + str(name))
                            else:
                                log("Ignoring tiling for: " + str(name))

        # Collect valid texture paths
        valid_dmaps = [d for d in set(dmaps) if d is not None]
        if additional:
            log("Adding additional images: " + ",".join(additional))
            valid_dmaps.extend(additional)

        if not valid_dmaps:
            msg = ("No valid texture files found. Make sure the texture images "
                   "referenced in the .mtl are present next to the .obj file.")
            if missing_basenames:
                msg += "\n\nExpected files (place these next to the .obj):\n"
                for bname in sorted(set(missing_basenames)):
                    msg += "  " + bname + "\n"
            raise PackError(msg)

        # Pack
        log("\nPacking textures...")
        output_image, uv_changes = pack_images(valid_dmaps, extents=textents)

        # Rewrite OBJ UVs
        log("Applying UV changes to OBJ...")
        outname = output_name + "_full.png"
        uv_lines = []
        curr_mtl = None
        new_obj_lines = []

        for line_idx, line in enumerate(obj_lines):
            if line.startswith("vt"):
                uv_lines.append(line_idx)
                new_obj_lines.append(line)
            elif line.startswith("usemtl"):
                curr_mtl = line[7:]
                new_obj_lines.append(line)
            elif line.startswith("f"):
                for vertex in line[2:].split():
                    v_def = vertex.split(sep="/")
                    if len(v_def) >= 2 and v_def[1]:
                        uv_idx = int(v_def[1]) - 1
                        uv_line_idx = uv_lines[uv_idx]
                        uv_line = obj_lines[uv_line_idx][3:]
                        uv = [float(u.strip()) for u in uv_line.split()]

                        if curr_mtl and curr_mtl in texmap and texmap[curr_mtl] in uv_changes:
                            changes = uv_changes[texmap[curr_mtl]]
                            uv[0] = uv[0] * changes["aspect"][0] + changes["offset"][0]
                            uv[1] = uv[1] * changes["aspect"][1] + changes["offset"][1]
                            new_obj_lines[uv_line_idx] = "vt {0} {1}".format(uv[0], uv[1])

                new_obj_lines.append(line)
            elif line.startswith("mtllib"):
                new_obj_lines.append("mtllib " + output_name + ".mtl")
            else:
                new_obj_lines.append(line)

        # Write output
        if output_dir is None:
            output_dir = os.path.join(wdir, output_name)
        else:
            output_dir = os.path.join(output_dir, output_name)
        os.makedirs(output_dir, exist_ok=True)

        obj_out = os.path.join(output_dir, output_name + ".obj")
        mtl_out = os.path.join(output_dir, output_name + ".mtl")
        tex_out = os.path.join(output_dir, outname)

        log("Writing output files:")
        log("  " + obj_out)
        log("  " + mtl_out)
        log("  " + tex_out)

        with open(obj_out, "w") as f:
            f.write("\n".join(new_obj_lines))
        with open(mtl_out, "w") as f:
            f.write("\n".join(new_mtl_lines))
        output_image.save(tex_out, format="PNG")

        log("\nDone! Output written to: " + output_dir)
        return output_dir

    finally:
        os.chdir(original_dir)
