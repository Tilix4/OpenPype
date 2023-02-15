"""Load an asset in Blender from an Alembic file."""
from pathlib import Path
from typing import Callable, List, Tuple

import bpy

from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.properties import OpenpypeContainer


class CacheModelLoader(plugin.AssetLoader):
    """Import cache models.

    Stores the imported asset in a collection named after the asset.

    Note:
        At least for now it only supports Alembic files.
    """

    families = ["model", "pointcache"]
    representations = ["abc"]

    label = "Import Alembic"
    icon = "download"
    color = "orange"
    order = 4

    load_type = "ABC"

    def _load_abc(
        self,
        libpath: Path,
        container_name: str,
        container: OpenpypeContainer = None,
    ) -> Tuple[OpenpypeContainer, List[bpy.types.ID]]:
        """Load ABC process.

        Args:
            libpath (Path): Path of ABC file to load.
            container_name (str): Name of container to link.
            container (OpenpypeContainer): Load into existing container.
                Defaults to None.

        Returns:
            Tuple[List[bpy.types.ID], OpenpypeContainer]:
                (Created scene container, Loaded datablocks)
        """

        current_objects = set(bpy.data.objects)

        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            bpy.ops.wm.alembic_import(filepath=libpath.as_posix())

        objects = set(bpy.data.objects) - current_objects

        for obj in objects:
            for collection in obj.users_collection:
                collection.objects.unlink(obj)

        return self._containerize_objects_in_collection(
            container_name, objects, container=container
        )

    def get_load_function(self) -> Callable:
        """Get appropriate function regarding the load type of the loader.

        Returns:
            Callable: Load function
        """
        return self._load_abc
