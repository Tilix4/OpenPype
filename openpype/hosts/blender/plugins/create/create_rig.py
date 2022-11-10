"""Create a rig asset."""
import bpy

import bpy

from openpype.pipeline import get_current_task_name
from openpype.hosts.blender.api import plugin, lib, ops
from openpype.hosts.blender.api.pipeline import AVALON_INSTANCES


class CreateRig(plugin.Creator):
    """Artist-friendly rig with controls to direct motion"""

    name = "rigMain"
    label = "Rig"
    family = "rig"
    icon = "wheelchair"
    defaults = ["Main", "Proxy"]
    color_tag = "COLOR_03"
    bl_types = frozenset(
        {bpy.types.Armature, bpy.types.Collection, bpy.types.Object}
    )
