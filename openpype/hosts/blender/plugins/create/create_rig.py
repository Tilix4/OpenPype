"""Create a rig asset."""

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
