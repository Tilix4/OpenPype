"""Load an asset in Blender from a FBX file."""

from pathlib import Path
from typing import Callable, List, Tuple

import bpy

from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.properties import OpenpypeContainer

class FbxLoader(plugin.Loader):
    """Import FBX.

    Stores the imported asset in a collection named after the asset.
    """
    representations = ["fbx"]

    icon = "download"
    color = "orange"
    order = 4

    scale_length = 0

    def _load_library_as_container(
        self,
        libpath: Path,
        container_name: str,
        container: OpenpypeContainer = None,
    ) -> Tuple[OpenpypeContainer, List[bpy.types.ID]]:

        current_objects = set(bpy.data.objects)

        hold_scale_length = bpy.context.scene.unit_settings.scale_length
        if self.scale_length > 0:
            bpy.context.scene.unit_settings.scale_length = self.scale_length

        bpy.ops.import_scene.fbx(filepath=libpath.as_posix())

        bpy.context.scene.unit_settings.scale_length = hold_scale_length

        objects = set(bpy.data.objects) - current_objects

        for obj in objects:
            for collection in obj.users_collection:
                collection.objects.unlink(obj)

        return self._containerize_objects_in_collection(
            container_name, objects, container=container
        )


class FbxModelLoader(FbxLoader):
    """Import FBX models.

    Stores the imported asset in a collection named after the asset.
    """
    label = "Import FBX"
    families = ["model", "rig"]


class FbxCameraLoader(FbxLoader):
    """Import a camera from a .fbx file.

    Stores the imported asset in a collection named after the asset.
    """
    families = ["camera"]
    label = "Import FBX Camera"
