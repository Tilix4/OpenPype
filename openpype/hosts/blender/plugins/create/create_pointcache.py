"""Create a pointcache asset."""

import bpy

from openpype.pipeline import get_current_task_name
import openpype.hosts.blender.api.plugin
from openpype.hosts.blender.api import lib


class CreatePointcache(plugin.Creator):
    """Polygonal static geometry"""

    name = "pointcacheMain"
    label = "Point Cache"
    family = "pointcache"
    icon = "gears"
