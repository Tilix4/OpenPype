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
    for datablock in list(bpy.data.libraries) + list(bpy.data.images):
        try:
            if (
                datablock
                and not datablock.is_library_indirect
                and not datablock.filepath.startswith("//")
            ):
                datablock.filepath = bpy.path.relpath(
                    str(Path(datablock.filepath).resolve()),
                    start=str(Path(bpy.data.filepath).parent.resolve()),
                )
        except (RuntimeError, ReferenceError, ValueError, OSError) as e:
            log.error(e)

    bpy.ops.wm.save_mainfile()
