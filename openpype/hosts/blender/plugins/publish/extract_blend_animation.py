import os

import bpy

import openpype.api
from openpype.hosts.blender.api import plugin


class ExtractBlendAnimation(openpype.api.Extractor):
    """Extract a blend file."""

    label = "Extract Blend"
    hosts = ["blender"]
    families = ["animation"]
    optional = True

    def process(self, instance):
        # Define extract output file path

        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.blend"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.info("Performing extraction..")

        data_blocks = set()
        collections = set()

        for obj in instance:
            if plugin.is_container(obj, family="rig"):
                collections.add(obj)

        for collection in collections:
            for obj in collection.all_objects:
                if obj.animation_data and obj.animation_data.action:
                    action = obj.animation_data.action.copy()
                    action_name = obj.animation_data.action.name.split(":")[-1]
                    action.name = f"{instance.name}:{action_name}"
                    action["collection"] = collection.name
                    action["armature"] = obj.name
                    data_blocks.add(action)

        bpy.data.libraries.write(filepath, data_blocks)

        for action in data_blocks:
            bpy.data.actions.remove(action)

        representation = {
            "name": "blend",
            "ext": "blend",
            "files": filename,
            "stagingDir": stagingdir,
        }
        instance.data.setdefault("representations", [])
        instance.data["representations"].append(representation)

        self.log.info(
            f"Extracted instance '{instance.name}' to: {representation}"
        )
