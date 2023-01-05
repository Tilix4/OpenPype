import bpy

from openpype.hosts.blender.api.pipeline import AVALON_PROPERTY
from openpype.pipeline import (
    InventoryAction,
)


class BreakOpenpypeReference(InventoryAction):

    label = "Break OpenPype reference"
    icon = "remove"
    color = "#ddbb00"
    order = -1

    update_version = -1

    def process(self, containers):

        openpype_containers = bpy.context.scene.openpype_containers
        for container in containers:

            container_name = container["objectName"]
            scene_container = openpype_containers.get(container_name)
            for d_ref in scene_container.datablock_refs:
                d_ref.datablock.pop(AVALON_PROPERTY, None)

            openpype_containers.remove(
                openpype_containers.find(container_name)
            )

        self.log.info(f"OpenPype References broken for: {containers}")
