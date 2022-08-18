from pathlib import Path

import bpy
from bpy.app.handlers import persistent

from openpype.lib.anatomy import Anatomy
from openpype.pipeline import install_host, legacy_io
from openpype.hosts.blender import api
from openpype.settings.lib import get_project_settings


@persistent
def setup_assets_library(*_args):
    """Activate and configure OpenPype's assets library in asset browser."""
    project_name = legacy_io.Session["AVALON_PROJECT"]
    project_settings = get_project_settings(project_name)
    blender_settings = project_settings.get("blender", {})
    assets_library_settings = blender_settings.get("assets-library")

    if not assets_library_settings:
        return

    if assets_library_settings.get("enabled", False):
        # Get OP asset library
        library = bpy.context.preferences.filepaths.asset_libraries.get(
            project_name
        )

        # Prepare anatomy data
        anatomy = Anatomy(project_name)
        anatomy_data = {
            "root": anatomy.roots,
            "project": {"name": project_name},
        }
        formatted_anatomy = anatomy.format(anatomy_data)

        # Build folder path
        library_folder_path = Path(
            formatted_anatomy["blenderAssetsLibrary"]["folder"]
        )

        # Add OP assets library to asset libraries filepaths
        if library:
            library.path = library_folder_path.as_posix()
        else:
            bpy.ops.preferences.asset_library_add(
                directory=library_folder_path.as_posix()
            )
            bpy.context.preferences.filepaths.asset_libraries[
                -1
            ].name = project_name

        # Set active assets library in Browser if any in workspace
        for assets_area in [
            a for a in bpy.context.screen.areas if a.ui_type == "ASSETS"
        ]:
            main_space = assets_area.spaces[0]

            # Set library
            main_space.params.asset_library_ref = project_name

            # Set import type
            main_space.params.import_type = assets_library_settings.get(
                "import_type", main_space.params.import_type
            )


def register():
    install_host(api)

    # Handlers
    bpy.app.handlers.load_post.append(setup_assets_library)


def unregister():
    # Remove OP assets library from asset libraries filepaths
    project_name = legacy_io.Session["AVALON_PROJECT"]
    lib_index = bpy.context.preferences.filepaths.asset_libraries.find(
        project_name
    )
    if lib_index >= 0:
        bpy.ops.preferences.asset_library_remove(index=lib_index)
