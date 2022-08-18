from pathlib import Path

import pyblish.api
from bpy.types import Collection

from openpype.pipeline.anatomy import Anatomy
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
    return blender_settings.get("assets-library", {}).get("enabled", False)


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
        NOTE: Only supports Collection type for assets because of OP's current implementation.

        Args:
            instance (List[Union[Collection, Object]]): List of integrated collections/objects
        """
        # Get instance useful data
        published_representations = instance.data.get(
            "published_representations"
        )

        # Get blend representation
        blend_representation = next(
            (
                r
                for r in published_representations.values()
                if r.get("anatomy_data", {}).get("app") == "blender"
            ),
            None,
        )
        if not blend_representation:
            return

        # Format anatomy for roots resolving
        project_name = legacy_io.Session["AVALON_PROJECT"]
        anatomy = Anatomy(project_name)
        formatted_anatomy = anatomy.format(
            blend_representation["anatomy_data"]
        )

        # Relevant resolved paths
        library_folder_path = Path(
            formatted_anatomy["blenderAssetsLibrary"]["folder"]
        )
        version_file = Path(
            blend_representation["representation"]["data"]["path"]
        )
        symlink_file = Path(library_folder_path, f"{instance.name}.blend")

        # Get related catalog files
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

        # Check assets library directory
        if not library_folder_path.is_dir():
            library_folder_path.mkdir(parents=True)

        # Check if file with same name exists and delete
        if symlink_file.is_file():
            symlink_file.unlink()

        # Get exisiting lines from library file
        if library_catalog_file.is_file():
            library_lines = library_catalog_file.read_text().splitlines()
        else:
            library_lines = []

        # Get all UUIDs from objects
        objects_uuids = tuple(
            obj.asset_data.catalog_id
            for obj in instance
            if isinstance(obj, Collection) and obj.asset_data
        )

        # Sort UUIDs in file to delete cleared assets
        if library_lines:
            with library_catalog_file.open("w") as file:
                kept_lines = [
                    l for l in library_lines if not l.startswith(objects_uuids)
                ]

                # Write lines with modifications
                file.write("\n".join(kept_lines) + "\n")

        # Check if any objects is marked as asset
        if not objects_uuids:
            return

        # Create symlink
        symlink_file.symlink_to(version_file)

        # Create/Update catalog references
        with library_catalog_file.open("w") as file:
            # Get source file text
            source_catalog_text = source_catalog_file.read_text()

            if library_lines:
                # Skip comments and version lines
                source_lines = [
                    l
                    for l in source_catalog_text.splitlines()
                    if l != "" and not l.startswith(("#", "Version"))
                ]

                # Update exisiting lines
                updated_lines = set()
                for line in source_lines:
                    # Update asset matched on UUID only if catalog ref has been changed
                    asset_uuid = line.split(":")[0]
                    for i, l in enumerate(library_lines):
                        if l.startswith(asset_uuid) and l != line:
                            library_lines[i] = line
                            updated_lines.add(line)
                            break

                # Add remaining lines
                library_lines.extend(set(source_lines) - updated_lines)

                # Write lines with modifications
                file.write("\n".join(library_lines) + "\n")
            else:
                # Copy source text
                file.write(source_catalog_text)
