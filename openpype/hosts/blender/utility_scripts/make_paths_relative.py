"""Make all paths relative."""

import bpy

from openpype.lib.log import Logger

if __name__ == "__main__":
    log = Logger().get_logger()
    log.debug(
        f"Blend file | All paths converted to relative: {bpy.data.filepath}"
    )

    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()
