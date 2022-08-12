"""Create an animation asset."""

import bpy

from openpype.pipeline import get_current_task_name
from openpype.hosts.blender.api import plugin, lib, ops
from openpype.hosts.blender.api.pipeline import AVALON_INSTANCES
from openpype.hosts.blender.api.lib import get_selection


class CreateAnimation(plugin.Creator):
    """Animation output for character rigs"""

    name = "animationMain"
    label = "Animation"
    family = "animation"
    icon = "male"
    color_tag = "COLOR_07"

    def _use_selection(self, container):
        selected_objects = set(get_selection())
        # Get rig collections from selected objects.
        selected_collections = set()
        for obj in list(selected_objects):
            for collection in obj.users_collection:
                if plugin.is_container(collection, "rig"):
                    selected_collections.add(collection)
                    selected_objects.remove(obj)

        plugin.link_to_collection(selected_collections, container)
        plugin.link_to_collection(selected_objects, container)

    def _process(self):
        # Get Instance Container
        container = super()._process()

        if (self.options or {}).get("members"):
            plugin.link_to_collection(self.options["members"], container)

        return container
