"""Create a model asset."""

import bpy

from openpype.pipeline import get_current_task_name
from openpype.hosts.blender.api import plugin, lib, ops
from openpype.hosts.blender.api.pipeline import AVALON_INSTANCES


class CreateModel(plugin.Creator):
    """Polygonal static geometry"""

    name = "modelMain"
    label = "Model"
    family = "model"
    icon = "cube"
    defaults = ["Main", "Proxy"]
    color_tag = "COLOR_04"
