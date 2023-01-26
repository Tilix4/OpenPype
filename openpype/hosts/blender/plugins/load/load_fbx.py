"""Load an asset in Blender from a FBX file."""

from pathlib import Path
from typing import Callable, List, Tuple
from string import digits

import bpy

from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.properties import OpenpypeContainer
from openpype.hosts.blender.api.utils import (
    link_to_collection,
    unlink_from_collection,
    get_parent_collection,
)
from openpype.hosts.blender.api.lib import (
    add_datablocks_to_container,
    create_container,
)


class FbxLoader(plugin.AssetLoader):
    """Import FBX.

    Stores the imported asset in a collection named after the asset.
    """
    representations = ["fbx"]

    label = "Import FBX"
    icon = "download"
    color = "orange"
    order = 4

    load_type = "FBX"
    scale_length = 0

    def _load_fbx(
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

        container_collection = None

        if container:
            container_collection = bpy.data.collections.get(container_name)

        if not container_collection:
            # Create collection container
            container_collection = bpy.data.collections.new(container_name)
            bpy.context.scene.collection.children.link(container_collection)
            # update name with occurence numbering
            container_name = container_collection.name

        link_to_collection(objects, container_collection)

        datablocks = list(objects)

        if container:
            # Add datablocks to container
            add_datablocks_to_container(datablocks, container)

            # Rename container
            if container.name != container_name:
                container.name = container_name
        else:
            # Create container if none providen
            container = create_container(container_name, datablocks)

        # Set data to container
        container.outliner_entity = container_collection

        return container, datablocks

    def get_load_function(self) -> Callable:
        """Get appropriate function regarding the load type of the loader.

        Returns:
            Callable: Load function
        """
        return self._load_fbx

    def replace_container(
        self,
        container: OpenpypeContainer,
        new_libpath: Path,
        new_container_name: str,
    ) -> Tuple[OpenpypeContainer, List[bpy.types.ID]]:
        """Replace container with datablocks from given libpath.

        Args:
            container (OpenpypeContainer): Container to replace datablocks of.
            new_libpath (Path): Library path to load datablocks from.
            new_container_name (str): Name of new container to load.

        Returns:
            Tuple[OpenpypeContainer, List[bpy.types.ID]]:
                (Container, List of loaded datablocks)
        """
        load_func = self.get_load_function()

        # Default behaviour to wipe and reload everything
        # but keeping same container
        if container.outliner_entity:
            parent_collection = get_parent_collection(
                container.outliner_entity
            )
        else:
            parent_collection = None

        # Keep current datablocks
        old_datablocks = {
            d_ref.datablock for d_ref in container.datablock_refs
        }

        # Clear container datablocks
        container.datablock_refs.clear()

        # Load new into same container
        container, datablocks = load_func(
            new_libpath,
            new_container_name,
            container=container,
        )

        # Old datablocks remap and deletion
        for old_datablock in old_datablocks:
            # Find matching new datablock by name without .###
            new_datablock = next(
                (
                    d
                    for d in datablocks
                    if old_datablock.name.rstrip(f".{digits}")
                    == d.name.rstrip(f".{digits}")
                ),
                None,
            )

            # Replace old by new datablock
            if new_datablock:
                original_datablock_name = old_datablock.name
                old_datablock.name += ".old"
                new_datablock.name = original_datablock_name
                old_datablock.make_local()
                old_datablock.user_remap(new_datablock)
            else:
                for collection in old_datablock.users_collection:
                    collection.objects.unlink(old_datablock)

        # Restore parent collection if existing
        if parent_collection:
            unlink_from_collection(
                container.outliner_entity,
                bpy.context.scene.collection
            )
            link_to_collection(
                container.outliner_entity,
                parent_collection
            )

        # clear unused datablock
        plugin.orphans_purge()

        return container, datablocks


class FbxModelLoader(FbxLoader):
    """Import FBX models.

    Stores the imported asset in a collection named after the asset.
    """
    families = ["model", "rig"]


class FbxCameraLoader(FbxLoader):
    """Import a camera from a .fbx file.

    Stores the imported asset in a collection named after the asset.
    """
    families = ["camera"]
    label = "Import FBX Camera"
