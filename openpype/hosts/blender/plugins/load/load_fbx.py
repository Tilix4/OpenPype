"""Load an asset in Blender from a FBX file."""

from pathlib import Path
from typing import List, Tuple

import bpy

from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.properties import OpenpypeContainer


class FbxModelLoader(plugin.AssetLoader):
    """Import FBX models.

    Stores the imported asset in a collection named after the asset.
    """

    families = ["model", "rig"]
    representations = ["fbx"]

    label = "Import FBX"
    icon = "download"
    color = "orange"
    order = 4

    load_type = "FBX"
    scale_length = 0

    def _load_fbx(
        self, libpath: Path,
        container_name: str,
        container: OpenpypeContainer = None,
    ) -> Tuple[OpenpypeContainer, List[bpy.types.ID]]:

        hold_scale_length = bpy.context.scene.unit_settings.scale_length
        if self.scale_length > 0:
            bpy.context.scene.unit_settings.scale_length = self.scale_length

        container, datablocks = super()._load_fbx(
            libpath, container_name, container
        )

        bpy.context.scene.unit_settings.scale_length = hold_scale_length

        return container, datablocks
