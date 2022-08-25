from pathlib import Path

import bpy

import openpype.api
from openpype.hosts.blender.api.lib import use_assets_library


class ExtractAssetsCatalog(openpype.api.Extractor):
    """Extract the assets catalog file next to blend file."""

    label = "Extract Assets Catalogs"
    hosts = ["blender"]
    # families = ["model", "camera", "rig", "action", "layout", "setdress"]
    optional = True
    active = use_assets_library()

    def process(self, instance):
        source_file = Path(bpy.data.filepath)
        source_catalog_file = source_file.parent.joinpath(
            "blender_assets.cats.txt"
        )

        # Check catalog file exists
        if not source_catalog_file.is_file():
            return

        instance.data.setdefault("transfers", [])
        instance.data["transfers"].append(
            (
                source_catalog_file.as_posix(),
                Path(
                    instance.data["publishDir"], source_catalog_file.name
                ).as_posix(),
            )
        )

        self.log.info(f"Extracted catalog file: {source_catalog_file}")
