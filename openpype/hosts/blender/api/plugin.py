"""Shared functionality for pipeline plugins for Blender."""

from pprint import pformat
from inspect import getmembers
from pathlib import Path
from contextlib import contextmanager, ExitStack
from typing import Dict, List, Optional
from collections.abc import Iterable

import bpy
from mathutils import Matrix

from openpype.pipeline import (
    legacy_io,
    LegacyCreator,
    LoaderPlugin,
    get_representation_path,
    AVALON_CONTAINER_ID,
)
from .ops import (
    MainThreadItem,
    execute_in_main_thread
)
from .lib import (
    imprint,
    get_selection
)
from .pipeline import metadata_update, AVALON_PROPERTY


VALID_EXTENSIONS = [".blend", ".json", ".abc", ".fbx"]


def asset_name(
    asset: str, subset: str, namespace: Optional[str] = None
) -> str:
    """Return a consistent name for an asset."""
    name = f"{asset}"
    if namespace:
        name = f"{name}_{namespace}"
    name = f"{name}_{subset}"
    return name


def get_unique_number(
    asset: str, subset: str
) -> str:
    """Return a unique number based on the asset name."""
    container_names = [c.name for c in bpy.data.collections]
    container_names += [
        obj.name
        for obj in bpy.data.objects
        if obj.instance_collection and obj.instance_type == 'COLLECTION'
    ]
    count = 1
    name = f"{asset}_{count:0>2}_{subset}"
    while name in container_names:
        count += 1
        name = f"{asset}_{count:0>2}_{subset}"
    return f"{count:0>2}"


def prepare_data(data, container_name=None):
    name = data.name
    local_data = data.make_local()
    if container_name:
        local_data.name = f"{container_name}:{name}"
    else:
        local_data.name = f"{name}"
    return local_data


def create_blender_context(active: Optional[bpy.types.Object] = None,
                           selected: Optional[bpy.types.Object] = None,):
    """Create a new Blender context. If an object is passed as
    parameter, it is set as selected and active.
    """

    if not isinstance(selected, list):
        selected = [selected]

    override_context = bpy.context.copy()

    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override_context['window'] = win
                        override_context['screen'] = win.screen
                        override_context['area'] = area
                        override_context['region'] = region
                        override_context['scene'] = bpy.context.scene
                        override_context['active_object'] = active
                        override_context['selected_objects'] = selected
                        return override_context
    raise Exception("Could not create a custom Blender context.")


def create_container(name, color_tag=None):
    """
    Create the container with the given name
    """
    # search in the container already exists
    container = bpy.data.collections.get(name)
    # if container doesn't exist create them
    if container is None:
        container = bpy.data.collections.new(name)
        if color_tag:
            container.color_tag = color_tag
        bpy.context.scene.collection.children.link(container)
        return container


def remove_container(container, content_only=False):
    """
    Remove the container with all this objects and child collections.

    Note:
        This rename all removed elements with .removed suffix to prevent
        naming conflict with created object before calling orphans_purge.
    """
    objects_to_remove = set()
    collections_to_remove = set()
    data_to_remove = set()
    materials_to_remove = set()

    if isinstance(container, bpy.types.Collection):
        # Append all objects in container collection to be removed.
        for obj in set(container.all_objects):
            objects_to_remove.add(obj)
            # Append original object if exists.
            if obj.original:
                objects_to_remove.add(obj.original)
        # Append all child collections in container to be removed.
        for child in set(container.children_recursive):
            collections_to_remove.add(child)
        # Append the container collection if content_only is False.
        if not content_only:
            collections_to_remove.add(container)
    else:
        # Append all child objects in container object.
        for obj in set(container.children_recursive):
            objects_to_remove.add(obj)
        # Append the container object if content_only is False.
        if not content_only:
            objects_to_remove.add(container)

    # Remove objects
    for obj in objects_to_remove:
        # Append object data if exists.
        if obj.data:
            data_to_remove.add(obj.data)
        obj.name = f"{obj.name}.removed"
        bpy.data.objects.remove(obj)
    # Remove objects
    for collection in collections_to_remove:
        collection.name = f"{collection.name}.removed"
        bpy.data.collections.remove(collection)
    # Remove data
    for data in data_to_remove:
        if data.users == 0:
            data.name = f"{data.name}.removed"
            # Append materials if data is mesh.
            if isinstance(data, bpy.types.Mesh):
                for mtl in data.materials:
                    if mtl:
                        materials_to_remove.add(mtl)
            # Remove data from this data collection type.
            for data_collection in (
                bpy.data.meshes,
                bpy.data.curves,
                bpy.data.lights,
                bpy.data.cameras,
                bpy.data.armatures,
            ):
                if data in data_collection.values():
                    data_collection.remove(data)
    # Remove materials
    for mtl in materials_to_remove:
        if mtl.users == 0:
            mtl.name = f"{mtl.name}.removed"
            bpy.data.materials.remove(mtl)


def get_container_objects(container):
    """Get the parent of the input collection"""
    if isinstance(container, bpy.types.Collection):
        objects = list(container.all_objects)
    else:
        objects = list(container.children_recursive)
        objects.append(container)
    return objects


def get_parent_collection(collection):
    """Get the parent of the input collection"""
    check_list = [bpy.context.scene.collection]

    for c in check_list:
        if collection.name in c.children.keys():
            return c
        check_list.extend(c.children)

    return None


def get_main_collection():
    """Get main collection.
        - the scene root collection if has no children.
        - the first collection if only child of root collection.
        - the only avalon instance collection child of root collection.
    """
    main_collection = bpy.context.scene.collection
    if len(main_collection.children) == 1:
        main_collection = main_collection.children[0]
    elif len(main_collection.children) > 1:
        instance_collections = [
            child
            for child in main_collection.children
            if (
                child.get(AVALON_PROPERTY) and
                child[AVALON_PROPERTY].get("id") == "pyblish.avalon.instance"
            )
        ]
        if len(instance_collections) > 1:
            instance_collections = [
                collection
                for collection in instance_collections
                if collection[AVALON_PROPERTY].get("family") not in (
                    "camera", "action", "pointcache"
                )
            ]
        if len(instance_collections) == 1:
            main_collection = instance_collections[0]

    return main_collection


def get_local_collection_with_name(name):
    for collection in bpy.data.collections:
        if collection.name == name and collection.library is None:
            return collection
    return None


def get_collections_by_objects(objects, collections=None):
    """Get collection from a collections list by objects."""
    if collections is None:
        collections = list(bpy.context.scene.collection.children)
    for collection in collections:
        if not len(collection.all_objects):
            continue
        elif all([obj in objects for obj in collection.all_objects]):
            yield collection
        elif len(collection.children):
            yield from get_collections_by_objects(objects, collection.children)


def link_to_collection(entity, collection):
    """link a entity to a collection. recursively if entity is iterable"""
    # Entity is Iterable, execute function recursively.
    if isinstance(entity, Iterable):
        for i in entity:
            link_to_collection(i, collection)
    # Entity is a Collection.
    elif (
        isinstance(entity, bpy.types.Collection) and
        entity not in collection.children.values() and
        collection not in entity.children.values() and
        entity is not collection
    ):
        collection.children.link(entity)
    # Entity is an Object.
    elif (
        isinstance(entity, bpy.types.Object) and
        entity not in collection.objects.values()
    ):
        collection.objects.link(entity)


def deselect_all():
    """Deselect all objects in the scene.

    Blender gives context error if trying to deselect object that it isn't
    in object mode.
    """
    modes = []
    active = bpy.context.view_layer.objects.active

    for obj in bpy.data.objects:
        if obj.mode != 'OBJECT':
            modes.append((obj, obj.mode))
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')

    for p in modes:
        bpy.context.view_layer.objects.active = p[0]
        bpy.ops.object.mode_set(mode=p[1])

    bpy.context.view_layer.objects.active = active


def orphans_purge():
    """Purge orphan datablocks and libraries."""
    # clear unused datablock
    while bpy.data.orphans_purge(do_local_ids=False, do_recursive=True):
        pass

    # clear unused libraries
    for library in list(bpy.data.libraries):
        if len(library.users_id) == 0:
            bpy.data.libraries.remove(library)


class Creator(LegacyCreator):
    """Base class for Creator plug-ins."""
    defaults = ['Main']
    color_tag = "NONE"

    def _process(self):
        # Get info from data and create name value.
        asset = self.data["asset"]
        subset = self.data["subset"]
        name = asset_name(asset, subset)

        # Create the container.

        container = create_container(name, self.color_tag)
        if container is None:
            raise RuntimeError(f"This instance already exists: {name}")

        # Add custom property on the instance container with the data.
        self.data["task"] = legacy_io.Session.get("AVALON_TASK")
        imprint(container, self.data)

        # Add selected objects to container if useSelection is True.
        if (self.options or {}).get("useSelection"):
            selected_objects = set(get_selection())
            # Get collection from selected objects.
            selected_collections = set()
            for collection in get_collections_by_objects(selected_objects):
                selected_collections.add(collection)
                selected_objects -= set(collection.all_objects)

            link_to_collection(selected_objects, container)
            link_to_collection(selected_collections, container)

            # Unlink from scene collection root if needed
            for obj in selected_objects:
                if obj in set(bpy.context.scene.collection.objects):
                    bpy.context.scene.collection.objects.unlink(obj)
            for collection in selected_collections:
                if collection in set(bpy.context.scene.collection.children):
                    bpy.context.scene.collection.children.unlink(collection)

        return container

    def process(self):
        """ Run the creator on Blender main thread"""
        mti = MainThreadItem(self._process)
        execute_in_main_thread(mti)


class Loader(LoaderPlugin):
    """Base class for Loader plug-ins."""

    hosts = ["blender"]


class AssetLoader(LoaderPlugin):
    """A basic AssetLoader for Blender

    This will implement the basic logic for linking/appending assets
    into another Blender scene.

    The `update` method should be implemented by a sub-class, because
    it's different for different types (e.g. model, rig, animation,
    etc.).
    """

    @staticmethod
    def _get_instance_empty(instance_name: str, nodes: List) -> Optional[bpy.types.Object]:
        """Get the 'instance empty' that holds the collection instance."""
        for node in nodes:
            if not isinstance(node, bpy.types.Object):
                continue
            if (node.type == 'EMPTY' and node.instance_type == 'COLLECTION'
                    and node.instance_collection and node.name == instance_name):
                return node
        return None

    @staticmethod
    def _get_instance_collection(instance_name: str, nodes: List) -> Optional[bpy.types.Collection]:
        """Get the 'instance collection' (container) for this asset."""
        for node in nodes:
            if not isinstance(node, bpy.types.Collection):
                continue
            if node.name == instance_name:
                return node
        return None

    @staticmethod
    def _get_library_from_container(container: bpy.types.Collection) -> bpy.types.Library:
        """Find the library file from the container.

        It traverses the objects from this collection, checks if there is only
        1 library from which the objects come from and returns the library.

        Warning:
            No nested collections are supported at the moment!
        """
        assert not container.children, "Nested collections are not supported."
        assert container.objects, "The collection doesn't contain any objects."
        libraries = set()
        for obj in container.objects:
            assert obj.library, f"'{obj.name}' is not linked."
            libraries.add(obj.library)

        assert len(
            libraries) == 1, "'{container.name}' contains objects from more then 1 library."

        return list(libraries)[0]

    @staticmethod
    def _get_container_from_collections(
        collections: List,
        famillies: Optional[List] = None
    ) -> Optional[bpy.types.Collection]:
        """Get valid container from loaded collections."""
        for collection in collections:
            metadata = collection.get(AVALON_PROPERTY)
            if (
                metadata and
                (not famillies or metadata.get("family") in famillies)
            ):
                return collection

    def _load_blend(self, libpath, asset_group):
        # Load collections from libpath library.
        with bpy.data.libraries.load(
            libpath, link=True, relative=False
        ) as (data_from, data_to):
            data_to.collections = data_from.collections

        # Get the right asset container from imported collections.
        container = self._get_container_from_collections(
            data_to.collections, self.families
        )
        assert container, "No asset container found"

        # Create override library for container and elements.
        override = container.override_hierarchy_create(
            bpy.context.scene, bpy.context.view_layer
        )

        # Move objects and child collections from override to asset_group.
        link_to_collection(override.objects, asset_group)
        link_to_collection(override.children, asset_group)

        # Clear and purge useless datablocks and selection.
        bpy.data.collections.remove(override)
        orphans_purge()
        deselect_all()

        return list(asset_group.all_objects)

    def process_asset(self,
                      context: dict,
                      name: str,
                      namespace: Optional[str] = None,
                      options: Optional[Dict] = None):
        """Must be implemented by a sub-class"""
        raise NotImplementedError("Must be implemented by a sub-class")

    def load(self,
             context: dict,
             name: Optional[str] = None,
             namespace: Optional[str] = None,
             options: Optional[Dict] = None) -> Optional[bpy.types.Collection]:
        """ Run the loader on Blender main thread"""
        mti = MainThreadItem(self._load, context, name, namespace, options)
        execute_in_main_thread(mti)

    def _load(
        self,
        context: dict,
        name: Optional[str] = None,
        namespace: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> Optional[bpy.types.Collection]:
        """Load asset via database

        Arguments:
            context: Full parenthood of representation to load
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            options: Additional settings dictionary
        """
        # TODO (jasper): make it possible to add the asset several times by
        # just re-using the collection
        assert Path(self.fname).exists(), f"{self.fname} doesn't exist."

        asset = context["asset"]["name"]
        subset = context["subset"]["name"]
        unique_number = get_unique_number(
            asset, subset
        )
        namespace = namespace or f"{asset}_{unique_number}"
        name = name or asset_name(
            asset, subset, unique_number
        )

        nodes = self.process_asset(
            context=context,
            name=name,
            namespace=namespace,
            options=options,
        )

        # Only containerise if anything was loaded by the Loader.
        if not nodes:
            return None

        # Only containerise if it's not already a collection from a .blend file.
        # representation = context["representation"]["name"]
        # if representation != "blend":
        #     from openpype.hosts.blender.api.pipeline import containerise
        #     return containerise(
        #         name=name,
        #         namespace=namespace,
        #         nodes=nodes,
        #         context=context,
        #         loader=self.__class__.__name__,
        #     )

        # asset = context["asset"]["name"]
        # subset = context["subset"]["name"]
        # instance_name = asset_name(asset, subset, unique_number) + '_CON'

        # return self._get_instance_collection(instance_name, nodes)

    def _is_updated(self, asset_group, object_name, libpath):
        """Check data before update. Return True if already updated"""

        assert asset_group, (
            f"The asset is not loaded: {object_name}"
        )
        assert libpath, (
            f"No existing library file found for {object_name}"
        )
        assert libpath.is_file(), (
            f"The file doesn't exist: {libpath}"
        )
        assert libpath.suffix.lower() in VALID_EXTENSIONS, (
            f"Unsupported file: {libpath}"
        )

        group_libpath = asset_group[AVALON_PROPERTY]["libpath"]

        normalized_group_libpath = (
            str(Path(bpy.path.abspath(group_libpath)).resolve())
        )
        normalized_libpath = (
            str(Path(bpy.path.abspath(str(libpath))).resolve())
        )
        self.log.debug(
            f"normalized_group_libpath:\n  {normalized_group_libpath}\n"
            f"normalized_libpath:\n  {normalized_libpath}"
        )
        return normalized_group_libpath == normalized_libpath

    def _update_blend(self, container: Dict, representation: Dict):
        """Update the loaded asset.

        This will remove all objects of the current collection, load the new
        ones and add them to the collection.
        If the objects of the collection are used in another collection they
        will not be removed, only unlinked. Normally this should not be the
        case though.

        Warning:
            No nested collections are supported at the moment!
        """
        object_name = container["objectName"]
        asset_group = (
            bpy.data.collections.get(object_name) or
            bpy.data.objects.get(object_name)
        )
        libpath = Path(get_representation_path(representation))

        self.log.info(
            "Container: %s\nRepresentation: %s",
            pformat(container, indent=2),
            pformat(representation, indent=2),
        )

        if self._is_updated(asset_group, object_name, libpath):
            self.log.info("Asset already up to date, not updating...")
            return

        with ExitStack() as stack:
            stack.enter_context(self.maintained_parent(asset_group))
            stack.enter_context(self.maintained_transforms(asset_group))
            stack.enter_context(self.maintained_modifiers(asset_group))
            stack.enter_context(self.maintained_constraints(asset_group))
            stack.enter_context(self.maintained_targets(asset_group))
            stack.enter_context(self.maintained_drivers(asset_group))
            stack.enter_context(self.maintained_actions(asset_group))

            remove_container(asset_group, content_only=True)
            objects = self._load_blend(str(libpath), asset_group)

        # update override library operations from asset objects
        for obj in objects:
            if obj.override_library:
                obj.override_library.operations_update()

        # clear orphan datablocks and libraries
        orphans_purge()
        deselect_all()

        # update metadata
        metadata_update(
            asset_group,
            {
                "libpath": str(libpath),
                "representation": str(representation["_id"]),
                "parent": str(representation["parent"]),
            }
        )

    def _update_metadata(
        self,
        asset_group: bpy.types.ID,
        context: dict,
        name: str,
        namespace: str,
        asset_name: str,
        libpath: str,
    ):
        metadata_update(
            asset_group,
            {
                "schema": "openpype:container-2.0",
                "id": AVALON_CONTAINER_ID,
                "name": name,
                "namespace": namespace or '',
                "loader": str(self.__class__.__name__),
                "representation": str(context["representation"]["_id"]),
                "libpath": libpath,
                "asset_name": asset_name,
                "parent": str(context["representation"]["parent"]),
                "family": context["representation"]["context"]["family"],
                "objectName": asset_group.name
            }
        )

    def exec_update(self, container: Dict, representation: Dict):
        """Must be implemented by a sub-class"""
        raise NotImplementedError("Must be implemented by a sub-class")

    def update(self, container: Dict, representation: Dict):
        """ Run the update on Blender main thread"""
        mti = MainThreadItem(self.exec_update, container, representation)
        execute_in_main_thread(mti)

    def exec_remove(self, container: Dict) -> bool:
        """Must be implemented by a sub-class"""
        raise NotImplementedError("Must be implemented by a sub-class")

    def remove(self, container: Dict) -> bool:
        """Run the remove on Blender main thread"""
        mti = MainThreadItem(self.exec_remove, container)
        execute_in_main_thread(mti)

    @staticmethod
    def _remove_container(container: Dict) -> bool:
        """Remove an existing container from a Blender scene.

        Arguments:
            container: Container to remove.

        Returns:
            bool: Whether the container was deleted.
        """
        object_name = container["objectName"]
        asset_group = (
            bpy.data.objects.get(object_name) or
            bpy.data.collections.get(object_name)
        )

        if not asset_group:
            return False

        remove_container(asset_group)
        orphans_purge()

        return True

    @contextmanager
    def maintained_parent(self, container):
        """Maintain parent during context."""
        container_objects = set(get_container_objects(container))
        scene_objects = set(bpy.data.objects) - container_objects
        objects_parents = dict()
        for obj in scene_objects:
            if obj.parent in container_objects:
                objects_parents[obj.name] = obj.parent.name
        for obj in container_objects:
            if obj.parent in scene_objects:
                objects_parents[obj.name] = obj.parent.name
        try:
            yield
        finally:
            # Restor parent.
            for obj_name, parent_name in objects_parents.items():
                obj = bpy.data.objects.get(obj_name)
                parent = bpy.data.objects.get(parent_name)
                if obj and parent and obj.parent is not parent:
                    obj.parent = parent

    @contextmanager
    def maintained_transforms(self, container):
        """Maintain transforms during context."""
        objects = get_container_objects(container)
        # Store transforms for all objects in container.
        objects_transforms = {
            obj.name: obj.matrix_basis.copy()
            for obj in objects
        }
        # Store transforms for all bones from armatures in container.
        bones_transforms = {
            obj.name: {
                bone.name: bone.matrix.copy()
                for bone in obj.pose.bones
            }
            for obj in objects
            if obj.type == "ARMATURE"
        }
        try:
            yield
        finally:
            # Restor transforms.
            for obj in bpy.data.objects:
                if obj.name in objects_transforms:
                    obj.matrix_basis = objects_transforms[obj.name]
                # Restor transforms for bones from armature.
                if obj.type == "ARMATURE" and obj.name in bones_transforms:
                    for bone in obj.pose.bones:
                        if bone.name in bones_transforms[obj.name]:
                            bone.matrix = (
                                bones_transforms[obj.name][bone.name]
                            )

    @contextmanager
    def maintained_modifiers(self, container):
        """Maintain modifiers during context."""
        objects = get_container_objects(container)
        objects_modifiers = [
            [ModifierDescriptor(modifier) for modifier in obj.modifiers]
            for obj in objects
        ]
        try:
            yield
        finally:
            # Restor modifiers.
            for modifiers in objects_modifiers:
                for modifier in modifiers:
                    modifier.restor()

    @contextmanager
    def maintained_constraints(self, container):
        """Maintain constraints during context."""
        objects = get_container_objects(container)
        objects_constraints = []
        armature_constraints = []
        for obj in objects:
            objects_constraints.append(
                [
                    ConstraintDescriptor(constraint)
                    for constraint in obj.constraints
                ]
            )
            if obj.type == "ARMATURE":
                armature_constraints.append(
                    {
                        bone.name: [
                            ConstraintDescriptor(constraint)
                            for constraint in bone.constraints
                        ]
                        for bone in obj.pose.bones
                    }
                )
        try:
            yield
        finally:
            # Restor modifiers.
            for constraints in objects_constraints:
                for constraint in constraints:
                    constraint.restor()
            for bones_constraints in armature_constraints:
                for bone_name, constraints in bones_constraints.items():
                    for constraint in constraints:
                        constraint.restor(bone_name=bone_name)

    @contextmanager
    def maintained_targets(self, container):
        """Maintain constraints during context."""
        container_objects = set(get_container_objects(container))
        scene_objects = set(bpy.data.objects) - container_objects
        stored_targets = []
        for obj in scene_objects:
            stored_targets += [
                (constraint, constraint.target.name)
                for constraint in obj.constraints
                if getattr(constraint, "target", None) in container_objects
            ]
            stored_targets += [
                (modifier, modifier.target.name)
                for modifier in obj.modifiers
                if getattr(modifier, "target", None) in container_objects
            ]
            # store constraint targets from bones in armatures
            if obj.type == "ARMATURE":
                for bone in obj.pose.bones:
                    stored_targets += [
                        (constraint, constraint.target.name)
                        for constraint in bone.constraints
                        if getattr(constraint, "target", None) in (
                            container_objects
                        )
                    ]
            # store driver variable targets from animation data
            if obj.animation_data:
                for driver in obj.animation_data.drivers:
                    for var in driver.driver.variables:
                        for target in var.targets:
                            if target.id in container_objects:
                                stored_targets.append(target, target.id.name)
        try:
            yield
        finally:
            # Restor targets.
            for entity, target_name in stored_targets:
                target = bpy.data.objects.get(target_name)
                if isinstance(entity, bpy.types.DriverTarget):
                    entity.id = target
                else:
                    entity.target = target

    @contextmanager
    def maintained_drivers(self, container):
        """Maintain drivers during context."""
        objects = get_container_objects(container)
        objects_drivers = {}
        objects_copies = []
        for obj in objects:
            if obj.animation_data and len(obj.animation_data.drivers):
                obj_copy = obj.copy()
                obj_copy.name = f"{obj_copy.name}.copy"
                obj_copy.use_fake_user = True
                objects_copies.append(obj_copy)
                objects_drivers[obj.name] = [
                    driver
                    for driver in obj_copy.animation_data.drivers
                ]
        try:
            yield
        finally:
            # Restor drivers.
            for obj_name, drivers in objects_drivers.items():
                obj = bpy.data.objects.get(obj_name)
                if not obj:
                    continue
                if not obj.animation_data:
                    obj.animation_data_create()
                for driver in drivers:
                    obj.animation_data.drivers.from_existing(src_driver=driver)
            # Clear copies.
            for obj_copy in objects_copies:
                obj_copy.use_fake_user = False
                bpy.data.objects.remove(obj_copy)

    @contextmanager
    def maintained_actions(self, container):
        """Maintain action during context."""
        objects = get_container_objects(container)
        actions = {}
        # Store actions from objects.
        for obj in objects:
            if obj.animation_data and obj.animation_data.action:
                actions[obj.name] = obj.animation_data.action
                obj.animation_data.action.use_fake_user = True
        try:
            yield
        finally:
            # Restor actions.
            for obj_name, action in actions.items():
                obj = bpy.data.objects.get(obj_name)
                if obj:
                    if obj.animation_data is None:
                        obj.animation_data_create()
                    obj.animation_data.action = action
            # Clear fake user.
            for action in actions.values():
                action.use_fake_user = False


class StructDescriptor:

    _invalid_property_names = [
        "__doc__",
        "__module__",
        "__slots__",
        "bl_rna",
        "rna_type",
        "name",
        "type",
        "is_override_data",
    ]

    def store_property(self, prop_name, prop_value):
        if isinstance(prop_value, bpy.types.Object):
            prop_value = f"bpy.data.objects:{prop_value.name}"
        elif isinstance(prop_value, Matrix):
            prop_value = prop_value.copy()
        self.properties[prop_name] = prop_value

    def restore_property(self, entity, prop_name):
        prop_value = self.properties.get(prop_name)
        if (
            isinstance(prop_value, str) and
            prop_value.startswith("bpy.data.objects:")
        ):
            prop_value = bpy.data.objects.get(
                prop_value.split("bpy.data.objects:")[-1]
            )
        setattr(entity, prop_name, prop_value)

    def __init__(self, bpy_struct: bpy.types.bpy_struct):
        self.name = bpy_struct.name
        self.type = bpy_struct.type
        self.object_name = bpy_struct.id_data.name
        self.is_override_data = bpy_struct.is_override_data

        self.properties = dict()
        for prop_name, prop_value in getmembers(bpy_struct):
            # filter the property
            if (
                prop_name in self._invalid_property_names or
                bpy_struct.is_property_readonly(prop_name)
            ):
                continue
            # store the property
            if (
                not bpy_struct.is_override_data or
                bpy_struct.is_property_overridable_library(prop_name)
            ):
                self.store_property(prop_name, prop_value)


class ModifierDescriptor(StructDescriptor):
    """
    Store the name, type, properties and object of a modifier.
    """

    def restor(self):
        obj = bpy.data.objects.get(self.object_name)
        if obj:
            modifier = obj.modifiers.get(self.name)
            if not modifier and not self.is_override_data:
                modifier = obj.modifiers.new(
                    self.name,
                    self.type,
                )
            if modifier and modifier.type == self.type:
                for prop_name in self.properties:
                    self.restore_property(modifier, prop_name)


class ConstraintDescriptor(StructDescriptor):
    """
    Store the name, type, properties and object of a constraint.
    """

    def restor(self, bone_name=None):
        obj = bpy.data.objects.get(self.object_name)
        if obj and obj.type == "ARMATURE" and bone_name:
            obj = obj.pose.bones.get(bone_name)
        if obj:
            constraint = obj.constraints.get(self.name)
            if not constraint and not self.is_override_data:
                constraint = obj.constraints.new(self.type)
                constraint.name = self.name
            if constraint and constraint.type == self.type:
                for prop_name in self.properties:
                    self.restore_property(constraint, prop_name)
