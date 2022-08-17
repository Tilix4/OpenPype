from pathlib import Path

import pyblish.api
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

        # Get required files
        source_file = Path(
            instance.data["versionEntity"]["data"]["source"].format_map(
                {"root": anatomy.roots}
            )
        )
        source_catalog_file = source_file.parent.joinpath(
            "blender_assets.cats.txt"
        )
        library_catalog_file = library_folder_path.joinpath(
            "blender_assets.cats.txt"
        )

        # Get exisiting lines from library file
        if library_catalog_file.is_file():
            library_lines = library_catalog_file.read_text().splitlines()
        else:
            library_lines = []

        with library_catalog_file.open("w") as file:
            # Get source file text
            source_catalog_text = source_catalog_file.read_text()

            if library_lines:
                # Iterate source file lines
                source_lines = source_catalog_text.splitlines()
                for line in source_lines:

                    # Skip comments and version line
                    if line == "" or line.startswith(("#", "Version")):
                        continue
                    # Update asset matched on UUID only if catalog ref has been changed
                    else:
                        asset_uuid = line.split(":")[0]
                        for i, l in enumerate(library_lines):
                            if l.startswith(asset_uuid) and l != line:
                                library_lines[i] = line

                # Write lines with modifications
                file.write("\n".join(library_lines) + "\n")
            else:
                # Copy source text
                file.write(source_catalog_text)
