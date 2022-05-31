import re
from pathlib import Path

import bpy
from bpy.app.handlers import persistent

from openpype.hosts.blender.api.utils import assign_loader_to_datablocks
from openpype.pipeline import install_host, legacy_io
from openpype.hosts.blender import api
from openpype.pipeline.anatomy import Anatomy
from openpype.pipeline.load.plugins import (
    discover_loader_plugins,
)
from openpype.settings.lib import get_project_settings


camel_case_first = re.compile(r"^[A-Z][a-z]*")

all_loaders = discover_loader_plugins()


@persistent
def loader_attribution_handler(*args):
    """Handler to attribute loader name to containers loaded outside of OP.

    For example if you link a container using Blender's file tools.
    """
    assign_loader_to_datablocks(
        [
            d
            for d in (
                bl_type
                for bl_type in dir(bpy.data)
                if not bl_type.startswith("__")
                and isinstance(bl_type, bpy.types.bpy_prop_collection)
                and len(bl_type)
            )
        ]
    )


@persistent
def instances_purge_handler(_):
    """Remove instances for which all datablocks have been removed."""
    scene = bpy.context.scene
    if not hasattr(scene, "openpype_instances"):
        return

    for op_instance in scene.openpype_instances:
        if not any({d_ref.datablock for d_ref in op_instance.datablock_refs}):
            scene.openpype_instances.remove(
                scene.openpype_instances.find(op_instance.name)
            )
            continue


@persistent
def setup_asset_library(*_args):
    """Activate OpenPype's assets library in asset browser."""
    project_name = legacy_io.Session["AVALON_PROJECT"]
    project_settings = get_project_settings(project_name)
    blender_settings = project_settings.get("blender", {})

    if blender_settings.get("blender-assets-library-enabled"):
        # Get OP asset library
        library = bpy.context.preferences.filepaths.asset_libraries.get(
            project_name
        )
        if not library:
            # Prepare anatomy data
            anatomy = Anatomy(project_name)
            anatomy_data = {
                "root": anatomy.roots,
                "project": {"name": project_name},
            }
            formatted_anatomy = anatomy.format(anatomy_data)

            # Build folder path
            library_folder_path = Path(
                formatted_anatomy["blender-assets-library"]["folder"]
            )

            # Add OP assets library to asset libraries filepaths
            bpy.ops.preferences.asset_library_add(
                directory=library_folder_path.as_posix()
            )
            bpy.context.preferences.filepaths.asset_libraries[
                -1
            ].name = project_name


def register():
    bpy.app.handlers.save_pre.append(loader_attribution_handler)
    bpy.app.handlers.save_pre.append(instances_purge_handler)

    install_host(api)

    # Handlers
    bpy.app.handlers.load_post.append(setup_asset_library)


def unregister():
    # Remove OP assets library from asset libraries filepaths
    project_name = legacy_io.Session["AVALON_PROJECT"]
    lib_index = bpy.context.preferences.filepaths.asset_libraries.find(
        project_name
    )
    if lib_index >= 0:
        bpy.ops.preferences.asset_library_remove(index=lib_index)
