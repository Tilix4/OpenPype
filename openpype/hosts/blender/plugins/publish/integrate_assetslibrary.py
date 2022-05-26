from pathlib import Path
from typing import List, Union

import pyblish.api
import bpy
from bpy.types import Collection, Object

from openpype.lib import Anatomy
from openpype.pipeline import legacy_io
from openpype.settings.lib import get_project_settings


def _use_assets_library() -> bool:
    """Check if use of assets library is enabled.

    Returns:
        bool: Is use of assets library enabled
    """
    project_name = legacy_io.Session["AVALON_PROJECT"]
    project_settings = get_project_settings(project_name)
    blender_settings = project_settings.get("blender", {})
    return blender_settings.get("blender-assets-library-enabled")


class IntegrateAssetsLibrary(pyblish.api.InstancePlugin):
    """Connecting version level dependency links"""

    order = pyblish.api.IntegratorOrder + 0.3
    label = "Add to assets library"
    hosts = ["blender"]
    families = ["model"]
    optional = True
    active = _use_assets_library()

    def process(self, instance: List[Union[Collection, Object]]):
        """Make collection available to be used from asset browser.
        
        Copy extracted blend file into folder dedicated for blender assets library.
        The collection is marked as `asset`.

        Args:
            instance (List[Union[Collection, Object]]): List of integrated collections/objects 
        """
        published_representations = instance.data.get("published_representations")
        project_name = legacy_io.Session["AVALON_PROJECT"]
        project_settings = get_project_settings(project_name)
        blender_settings = project_settings.get("blender", {})

        # Stop if disabled or Instance is without representations
        if (
            not blender_settings.get("blender-assets-library-enabled")
            or not published_representations
        ):
            return

        # Anatomy is primarily used for roots resolving
        anatomy = Anatomy(project_name)

        # Extract asset filename from published representations
        # NOTE this is not a clean way to do it,
        # but making it simple this will require deep OP refactor
        library_folder_path = ""
        asset_filename = ""
        for representation_info in published_representations.values():
            anatomy_data = representation_info["anatomy_data"]

            # Representation was not integrated
            if not anatomy_data:
                continue

            # Get assets library path folder
            if anatomy_data.get("app") in self.hosts:
                formatted_anatomy = anatomy.format(anatomy_data)
                library_folder_path = Path(
                    formatted_anatomy["blender-assets-library"]["folder"]
                )
                asset_filename = Path(library_folder_path, f"{instance.name}.blend")
                break

        # Mark as asset
        marked_as_assets = []
        for obj in instance:
            if isinstance(obj, Collection):
                obj.asset_mark()
                marked_as_assets.append(obj)

        # Save asset library
        if not library_folder_path.is_dir():
            asset_filename.mkdir(parents=True)
        bpy.ops.wm.save_as_mainfile(filepath=asset_filename.as_posix(), copy=True)

        # Unmark assets to avoid having it
        [b.asset_clear() for b in marked_as_assets]
