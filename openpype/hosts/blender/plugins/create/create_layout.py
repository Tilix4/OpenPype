"""Create a layout asset."""

import bpy

from openpype.pipeline import get_current_task_name
from openpype.hosts.blender.api import plugin, lib, ops
from openpype.hosts.blender.api.pipeline import AVALON_INSTANCES


class CreateLayout(plugin.Creator):
    """A grouped package of loaded content"""

    name = "layoutMain"
    label = "Layout"
    family = "layout"
    icon = "cubes"
    defaults = ["Main", "FromAnimation"]
