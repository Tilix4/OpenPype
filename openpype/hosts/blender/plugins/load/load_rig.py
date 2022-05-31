"""Load a rig asset in Blender."""

import contextlib
from pathlib import Path
from typing import Dict, List, Optional

import bpy

from openpype import lib
from openpype.pipeline import legacy_io, legacy_create, AVALON_CONTAINER_ID
from openpype.hosts.blender.api import plugin, get_selection
from openpype.hosts.blender.api.pipeline import AVALON_PROPERTY


class BlendRigLoader(plugin.AssetLoader):
    """Load rigs from a .blend file."""

    families = ["rig"]
    representations = ["blend"]

    label = "Link Rig"
    icon = "code-fork"
    color = "orange"
    color_tag = "COLOR_03"

    @staticmethod
    def _is_model_container(collection):
        return (
            collection.get(AVALON_PROPERTY) and
            collection[AVALON_PROPERTY].get("family") == "model" and
            collection[AVALON_PROPERTY].get("id") == AVALON_CONTAINER_ID
        )

    def _process(self, libpath, asset_group):
        # Load blend from from libpath library.
        objects = self._load_blend(libpath, asset_group)

        # Rename loaded collections with asset group name prefix.
        for child in set(asset_group.children_recursive):
            child.name = f"{asset_group.name}:{child.name}"
            # Disable selection for modeling container.
            if self._is_model_container:
                child.hide_select = True

        # Rename loaded objects and their dependencies with asset group name
        # as namespace prefix.
        self._rename_objects_with_namespace(objects, asset_group.name)

        return objects

    @staticmethod
    def _assign_actions(objects, namespace):
        """Assign new action for all objects from linked rig."""

        task = legacy_io.Session.get("AVALON_TASK")
        asset = legacy_io.Session.get("AVALON_ASSET")

        # If rig contain only one armature.
        armatures = [obj for obj in objects if obj.type == "ARMATURE"]
        if len(armatures) == 1:
            armature = armatures[0]
            if armature.animation_data is None:
                armature.animation_data_create()
            armature.animation_data.action = bpy.data.actions.new(
                f"{asset}_{task}:{namespace}_action"
            )

        # If rig contain multiple armatures, we generate actions for
        # each armature.
        elif armatures:
            for armature in armatures:
                if armature.animation_data is None:
                    armature.animation_data_create()
                action_name = armature.name.replace(":", "_")
                armature.animation_data.action = bpy.data.actions.new(
                    f"{asset}_{task}:{action_name}_action"
                )

        # If rig contain no armature we generate actions for each object.
        else:
            for obj in objects:
                if obj.animation_data is None:
                    obj.animation_data_create()
                action_name = obj.name.replace(":", "_")
                obj.animation_data.action = bpy.data.actions.new(
                    f"{asset}_{task}:{action_name}_action"
                )
        plugin.orphans_purge()

    @staticmethod
    def _apply_options(asset_group, options, namespace):
        """Apply load options fro asset_group."""

        task = legacy_io.Session.get("AVALON_TASK")
        asset = legacy_io.Session.get("AVALON_ASSET")

        if options.get("create_animation"):
            creator_plugin = lib.get_creator_by_name("CreateAnimation")
            if not creator_plugin:
                raise ValueError(
                    'Creator plugin "CreateAnimation" was not found.'
                )

            context = options.get("create_context")
            representation = str(context["representation"]["_id"])

            legacy_create(
                creator_plugin,
                name=f"{namespace}_animation",
                asset=context["asset"]["name"],
                options={"useSelection": False, "asset_group": asset_group},
                data={"dependencies": representation}
            )

        anim_file = options.get('animation_file')
        if isinstance(anim_file, str) and Path(anim_file).is_file():

            bpy.ops.import_scene.fbx(filepath=anim_file, anim_offset=0.0)
            imported = get_selection()

            armature = None
            for obj in asset_group.all_objects:
                if obj.type == 'ARMATURE':
                    armature = obj

            if not armature:
                raise Exception(f"Armature not found for {asset_group.name}")

            for obj in imported:
                if obj.type == 'ARMATURE':
                    if not armature.animation_data:
                        armature.animation_data_create()
                    armature.animation_data.action = obj.animation_data.action
                    armature.animation_data.action.name = (
                        f"{asset}_{task}:{namespace}_action"
                    )

            for obj in imported:
                bpy.data.objects.remove(obj)

        action = options.get('action')
        if isinstance(action, bpy.types.Action):
            for obj in asset_group.all_objects:
                if obj.type == 'ARMATURE':
                    if not armature.animation_data:
                        armature.animation_data_create()
                    armature.animation_data.action = action

        parent = options.get('parent')
        if isinstance(parent, bpy.types.Collection):
            current_parent = plugin.get_parent_collection(asset_group)
            if current_parent:
                current_parent.children.unlink(asset_group)
            plugin.link_to_collection(asset_group, parent)

    def process_asset(
        self,
        context: dict,
        name: str,
        namespace: Optional[str] = None,
        options: Optional[Dict] = None
    ) -> List:
        """Asset loading Process"""
        asset_group, objects = super().process_asset(context, name, namespace)
        asset_group.color_tag = self.color_tag

        namespace = asset_group[AVALON_PROPERTY]["namespace"]
        self._assign_actions(objects, namespace)

        if options is not None:
            self._apply_options(asset_group, options, namespace)

        return objects

    def exec_update(self, container: Dict, representation: Dict):
        """Update the loaded asset"""
        self._update_process(container, representation)

        # Ensure updated rig has action.
        collection = bpy.data.collections.get(container["objectName"])
        if collection:
            self._assign_actions(
                collection.all_objects, container["namespace"]
            )

    def exec_remove(self, container) -> bool:
        """Remove the existing container from Blender scene"""
        return self._remove_container(container)

    @contextlib.contextmanager
    def maintained_actions(self, asset_group):
        """Maintain actions during context."""
        asset_group_name = asset_group.name
        objects_actions = []
        armature_action = None
        # Get the armature from asset_group.
        armatures = [
            obj
            for obj in asset_group.all_objects
            if obj.type == "ARMATURE"
        ]
        # Store action from armature.
        if (
            len(armatures) == 1 and
            armatures[0].animation_data and
            armatures[0].animation_data.action
        ):
            armature_action = armatures[0].animation_data.action
        else:
            # If there is no or multiple armature or no action from armature,
            # we get actions from all objects from asset_group.
            for obj in asset_group.all_objects:
                if obj.animation_data and obj.animation_data.action:
                    objects_actions[obj.name] = obj.animation_data.action
        try:
            yield
        finally:
            # Restor action.
            asset_group = bpy.data.collections.get(asset_group_name)
            if asset_group:
                if armature_action:
                    for obj in asset_group.all_objects:
                        if obj.type == "ARMATURE":
                            if obj.animation_data is None:
                                obj.animation_data_create()
                            obj.animation_data.action = armature_action
                elif objects_actions:
                    for obj in asset_group.all_objects:
                        action = objects_actions.get(obj.name)
                        if action:
                            if obj.animation_data is None:
                                obj.animation_data_create()
                            obj.animation_data.action = action
