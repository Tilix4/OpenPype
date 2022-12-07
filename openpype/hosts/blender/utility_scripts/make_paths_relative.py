"""Make all paths relative."""

from pathlib import Path
import bpy

from openpype.lib.log import Logger

if __name__ == "__main__":
    log = Logger().get_logger()
    log.debug(
        f"Blend file | All paths converted to relative: {bpy.data.filepath}"
    )
    # Resolve path from source filepath with the relative filepath
    # TODO make it a common list
    datablocks_with_filepath = list(bpy.data.libraries) + list(bpy.data.images)
    for datablock in datablocks_with_filepath:
        try:
            datablock.filepath = bpy.path.relpath(
                str(Path(datablock.filepath).resolve()),
                start=str(Path(bpy.data.filepath).parent.resolve()),
            )
        except (RuntimeError, ValueError) as e:
            log.error(e)

    bpy.ops.wm.save_mainfile()
