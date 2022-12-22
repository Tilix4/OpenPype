"""Shared functionalities for Blender files data manipulation."""
from typing import List, Optional, Set, Union, Iterator
from collections.abc import Iterable

import bpy
from openpype.pipeline.constants import AVALON_CONTAINER_ID, AVALON_INSTANCE_ID
from openpype.pipeline.load.plugins import (
    LoaderPlugin,
    discover_loader_plugins,
)
from openpype.pipeline.load.utils import loaders_from_repre_context


# Key for metadata dict
AVALON_PROPERTY = "avalon"

# Match Blender type to a datapath to look into. Needed for native UI creator.
BL_TYPE_DATAPATH = (  # TODO rename DATACOL
    {  # NOTE Order is important for some hierarchy based processes!
        bpy.types.Collection: "collections",  # NOTE Must be always first
        bpy.types.Object: "objects",
        bpy.types.Camera: "cameras",
        bpy.types.Action: "actions",
        bpy.types.Armature: "armatures",
        bpy.types.Material: "materials",
        bpy.types.GeometryNodeTree: "node_groups",
        bpy.types.ParticleSettings: "particles",
        bpy.types.World: "worlds",
    }
)
# Match Blender type to an ICON for display
BL_TYPE_ICON = {
    bpy.types.Collection: "OUTLINER_COLLECTION",
    bpy.types.Object: "OBJECT_DATA",
    bpy.types.Camera: "CAMERA_DATA",
    bpy.types.Action: "ACTION",
    bpy.types.Armature: "ARMATURE_DATA",
    bpy.types.Material: "MATERIAL_DATA",
    bpy.types.GeometryNodeTree: "NODETREE",
    bpy.types.ParticleSettings: "PARTICLES",
    bpy.types.World: "WORLD_DATA",
}
# Types which can be handled through the outliner
BL_OUTLINER_TYPES = frozenset((bpy.types.Collection, bpy.types.Object))


def get_children_recursive(
    entity: Union[bpy.types.Collection, bpy.types.Object]
) -> Iterator[Union[bpy.types.Collection, bpy.types.Object]]:
    """Get childrens recursively from a object or a collection.

    Arguments:
        entity: The parent entity.

    Yields:
        The next childrens from parent entity.
    """
    # Since Blender 3.1.0 we can use "children_recursive" attribute.
    if hasattr(entity, "children_recursive"):
        for child in entity.children_recursive:
            yield child
    else:
        for child in entity.children:
            yield child
            yield from get_children_recursive(child)


def get_all_outliner_children(
    entity: Union[bpy.types.Collection, bpy.types.Object]
) -> Set[Union[bpy.types.Collection, bpy.types.Object]]:
    """Get all outliner children of an outliner entity.

    For a Collection, it is both objects and children collections.
    For an Object, only objects parented to the given one.

    Args:
        entity (Union[bpy.types.Collection, bpy.types.Object]): Outliner entity to get children from.

    Returns:
        Set[Union[bpy.types.Collection, bpy.types.Object]]: All outliner children.
    """
    if not entity:
        return set()

    if hasattr(entity, "all_objects"):
        return set(entity.children_recursive) | set(entity.all_objects)
    else:
        return set(entity.children_recursive)


def get_parent_collection(
    entity: Union[bpy.types.Collection, bpy.types.Object],
) -> Optional[bpy.types.Collection]:
    """Get the parent of the input outliner entity (collection or object).

    Args:
        entity (Union[bpy.types.Collection, bpy.types.Object]):
            Collection to get parent of.

    Returns:
        Optional[bpy.types.Collection]: Parent of entity
    """
    scene_collection = bpy.context.scene.collection
    if entity.name in scene_collection.children:
        return scene_collection
    # Entity is a Collection.
    elif isinstance(entity, bpy.types.Collection):
        for col in scene_collection.children_recursive:
            if entity.name in col.children:
                return col
    # Entity is an Object.
    elif isinstance(entity, bpy.types.Object):
        for col in scene_collection.children_recursive:
            if entity.name in col.objects:
                return col


def get_instanced_collections() -> Set[bpy.types.Collection]:
    """Get all instanced collections from context scene.

    Returns:
        Set[bpy.types.Collection]: Instanced collections in current scene.
    """
    return {
        obj.instance_collection
        for obj in bpy.context.scene.objects
        if obj.is_instancer and obj.instance_collection.library
    }


def link_to_collection(
    entity: Union[bpy.types.Collection, bpy.types.Object, Iterator],
    collection: bpy.types.Collection,
):
    """link an entity to a collection.

    Note:
        Recursive function if entity is iterable.

    Arguments:
        entity: The collection, object or list of valid entities who need to be
            parenting with the given collection.
        collection: The collection used for parenting.
    """
    # Entity is Iterable, execute function recursively.
    if isinstance(entity, Iterable):
        for i in entity:
            link_to_collection(i, collection)
    # Entity is a Collection.
    elif (
        isinstance(entity, bpy.types.Collection)
        and entity not in collection.children.values()
        and collection not in entity.children.values()
        and entity is not collection
    ):
        collection.children.link(entity)
    # Entity is an Object.
    elif (
        isinstance(entity, bpy.types.Object)
        and entity not in collection.objects.values()
        and entity.instance_collection is not collection
        and entity.instance_collection
        not in set(get_children_recursive(collection))
    ):
        collection.objects.link(entity)


def unlink_from_collection(
    entity: Union[bpy.types.Collection, bpy.types.Object, Iterator],
    collection: bpy.types.Collection,
):
    """Unlink an entity from a collection.

    Note:
        Recursive function if entity is iterable.

    Args:
        entity (Union[bpy.types.Collection, bpy.types.Object, Iterator]): The collection, object or list of valid entities who need to be
            parenting with the given collection.
        collection (bpy.types.Collection): The collection to remove parenting.
    """
    # Entity is Iterable, execute function recursively.
    if isinstance(entity, Iterable):
        for i in entity:
            unlink_from_collection(i, collection)
    # Entity is a Collection.
    elif isinstance(entity, bpy.types.Collection) and entity is not collection:
        collection.children.unlink(entity)
    # Entity is an Object.
    elif isinstance(entity, bpy.types.Object):
        collection.objects.unlink(entity)


def get_loader_name(loaders: List[LoaderPlugin], load_type: str) -> str:
    """Get loader name from list by requested load type.

    Args:
        loaders (List[LoaderPlugin]): List of available loaders
        load_type (str): Load type to get loader of

    Returns:
        str: Loader name
    """
    return next(
        (l.__name__ for l in loaders if l.__name__.startswith(load_type)),
        None,
    )


def assign_loader_to_datablocks(datablocks: List[bpy.types.ID]):
    """Assign loader name to container datablocks loaded outside of OP.

    For example if you link a container using Blender's file tools.

    Args:
        datablocks (List[bpy.types.ID]): Datablocks to assign loader to.
    """
    datablocks_to_skip = set()
    all_loaders = discover_loader_plugins()
    all_instanced_collections = get_instanced_collections()
    for datablock in datablocks:
        if datablock in datablocks_to_skip:
            continue

        # Get avalon data
        avalon_data = datablock.get(AVALON_PROPERTY)
        if not avalon_data or avalon_data.get("id") == AVALON_INSTANCE_ID:
            continue

        # Skip all children of container
        if hasattr(datablock, "children_recursive"):
            datablocks_to_skip.update(datablock.children_recursive)
        if hasattr(datablock, "all_objects"):
            datablocks_to_skip.update(datablock.all_objects)

        # Get available loaders
        context = {
            "subset": {"schema": AVALON_CONTAINER_ID},
            "version": {"data": {"families": [avalon_data["family"]]}},
            "representation": {"name": "blend"},
        }
        loaders = loaders_from_repre_context(all_loaders, context)

        if datablock.library:
            # Instance loader, an instance in OP is necessarily a link
            if datablock in all_instanced_collections:
                datablock[AVALON_PROPERTY]["loader"] = get_loader_name(
                    loaders, "Instance"
                )
            # Link loader
            else:
                datablock[AVALON_PROPERTY]["loader"] = get_loader_name(
                    loaders, "Link"
                )
        else:  # Append loader
            datablock[AVALON_PROPERTY]["loader"] = get_loader_name(
                loaders, "Append"
            )
