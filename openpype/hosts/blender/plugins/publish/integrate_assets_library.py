from pathlib import Path

import pyblish.api
from bpy.types import Collection
from openpype.client.entities import get_project_connection, get_subset_by_name
from openpype.hosts.blender.api.lib import (
    build_catalog_file,
    use_assets_library,
    resolve_assets_library_path,
)

from openpype.pipeline.anatomy import Anatomy
from openpype.pipeline import legacy_io


class IntegrateAssetsLibrary(pyblish.api.InstancePlugin):
    """Connecting version level dependency links"""

    order = pyblish.api.IntegratorOrder + 0.3
    label = "Add to assets library"
    hosts = ["blender"]
    families = ["model"]
    optional = True
    active = use_assets_library()

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

        # Collect collections marked as assets
        collections_marked_as_assets = {
            obj
            for obj in instance
            if isinstance(obj, Collection) and obj.asset_data
        }
        if not collections_marked_as_assets:
            return

        # Format anatomy for roots resolving
        project_name = legacy_io.Session["AVALON_PROJECT"]
        anatomy = Anatomy(project_name)

        # Relevant resolved paths
        version_file = Path(
            blend_representation["representation"]["data"]["path"]
        )
        symlink_file = resolve_assets_library_path(
            anatomy, blend_representation["anatomy_data"]
        )

        # Check assets library directory
        if not symlink_file.parent.is_dir():
            symlink_file.parent.mkdir(parents=True)

        # Check if file with same name exists and delete
        if symlink_file.is_file():
            symlink_file.unlink()

        # Create symlink
        symlink_file.symlink_to(version_file)

        # Keep marked as asset information in DB
        dbcon = get_project_connection(project_name)
        subset = get_subset_by_name(
            project_name,
            subset_name=instance.data["subset"],
            asset_id=instance.data["assetEntity"]["_id"],
        )
        dbcon.update_one(
            {"_id": subset["_id"]},
            {"$set": {"data.blender.marked_as_asset": True}},
        )

        # Get exisiting lines from library file
        library_catalog_file = symlink_file.parent.joinpath(
            "blender_assets.cats.txt"
        )
        if library_catalog_file.is_file():
            library_lines = library_catalog_file.read_text().splitlines()
        else:
            library_lines = []

        # Get all UUIDs from objects
        objects_uuids = tuple(
            obj.asset_data.catalog_id for obj in collections_marked_as_assets
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

        source_file = Path(
            instance.data["versionEntity"]["data"]["source"].format_map(
                {"root": anatomy.roots}
            )
        )
        symlink_file = resolve_assets_library_path(
            anatomy, blend_representation["anatomy_data"]
        )
        build_catalog_file(source_file, library_catalog_file)
