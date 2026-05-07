#!/usr/bin/env python3

# The MIT License (MIT)
# Copyright (c) 2015 Luke Gaynor
# See LICENSE for details.

import argparse
import os
import sys
from packer import run_pack, PackError


def strtobool(val):
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError("invalid truth value %r" % (val,))


def cli_tile_callback(texture_name, h_tiles, v_tiles):
    print("\nWARNING: The following texture has coordinates that imply "
          "it tiles {}x{} times:\n\t{}".format(h_tiles, v_tiles, texture_name))
    print("This may be intentional (i.e. tank track textures), or a "
          "sign of problematic UV coordinates.")
    print("(If you are unsure, just hit enter to answer 'No')")
    try:
        return strtobool(input("Do you want to unroll this wrapping "
                               "by tiling the texture? [y/N]: "))
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Pack OBJ textures into a single atlas"
    )
    parser.add_argument("obj", help="path to the .obj file")
    parser.add_argument("-m", "--material", help="path to the .mtl file")
    parser.add_argument("-o", "--output",
                        help="output name, used for image and folder")
    parser.add_argument("-a", "--add", nargs="+",
                        help="any additional images to pack")
    parser.add_argument('--no-crop', dest='crop', action='store_false',
                        help="do not attempt to crop textures")
    parser.add_argument('--no-tile', dest='tile', action='store_false',
                        help="do not attempt to tile textures outside UV space")
    parser.add_argument('--no-wrap', dest='wrap', action='store_false',
                        help="don't shift remaining UV verts into [0,1] space")
    parser.set_defaults(crop=True, tile=True, wrap=True)

    args = parser.parse_args()

    additional = None
    if args.add:
        additional = [os.path.realpath(a) for a in args.add]

    try:
        run_pack(
            obj_path=args.obj,
            mtl_path=args.material,
            output_name=args.output,
            crop=args.crop,
            tile=args.tile,
            wrap=args.wrap,
            additional=additional,
            tile_callback=cli_tile_callback if args.tile else None,
            log_callback=print,
        )
        print("\nRemember to convert the final packed texture into a "
              "JPEG if you do not need the transparency.")
    except PackError as e:
        print("\nERROR: " + str(e), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
