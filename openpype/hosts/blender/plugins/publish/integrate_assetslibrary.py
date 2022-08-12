from pathlib import Path
from pprint import pprint

import pyblish.api
import bpy
from bpy.types import Collection

from openpype.pipeline.anatomy import Anatomy
from openpype.pipeline import legacy_io
from openpype.settings.lib import get_project_settings

print("lala")


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

    def process(self, instance):
        """Make collection marked as asset available to be used from asset browser.

        Symlink hero blend file into folder dedicated for blender assets library.

        Args:
            instance (List[Union[Collection, Object]]): List of integrated collections/objects
        """
        marked_as_assets = [
            obj
            for obj in instance
            if isinstance(obj, Collection) and obj.asset_data
        ]

        # Check if marked as asset
        if not marked_as_assets:
            return

        # Get instance useful data
        published_representations = instance.data.get(
            "published_representations"
        )
        project_name = legacy_io.Session["AVALON_PROJECT"]

        # Stop if disabled or Instance is without representations
        if not published_representations:
            return

        # Anatomy is primarily used for roots resolving
        anatomy = Anatomy(project_name)

        # Extract asset filename from published representations
        library_folder_path = ""
        symlink_file = ""
        for representation_data in published_representations.values():
            anatomy_data = representation_data["anatomy_data"]

            # Representation was not integrated
            if not anatomy_data:
                continue

            # Get assets library path folder & hero file path
            if anatomy_data.get("app") in self.hosts:
                formatted_anatomy = anatomy.format(anatomy_data)
                library_folder_path = Path(
                    formatted_anatomy["blenderAssetsLibrary"]["folder"]
                )
                version_file = Path(
                    representation_data["representation"]["data"]["path"]
                )
                symlink_file = Path(
                    library_folder_path, f"{instance.name}.blend"
                )
                break

        # Check assets library directory
        if not library_folder_path.is_dir():
            library_folder_path.mkdir(parents=True)

        # Create symlink
        if symlink_file.is_file():  # Delete existing one if any
            symlink_file.unlink()
        symlink_file.symlink_to(version_file)
