import os

import bpy
from bson.objectid import ObjectId

import openpype.api
from openpype.pipeline import discover_loader_plugins, AVALON_CONTAINER_ID
from openpype.pipeline.load.utils import loaders_from_repre_context
from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.pipeline import (
    metadata_update,
    AVALON_PROPERTY,
)


class ExtractBlend(openpype.api.Extractor):
    """Extract a blend file."""

    label = "Extract Blend"
    hosts = ["blender"]
    families = ["model", "camera", "rig", "action", "layout", "setdress"]
    optional = True

    @staticmethod
    def _pack_images_from_objects(objects):
        """Pack images from mesh objects materials."""
        # Get all objects materials using node tree shader.
        materials = set()
        for obj in objects:
            for mtl_slot in obj.material_slots:
                if (
                    mtl_slot.material
                    and mtl_slot.material.use_nodes
                    and mtl_slot.material.node_tree.type == "SHADER"
                ):
                    materials.add(mtl_slot.material)
        # Get ShaderNodeTexImage from material node_tree.
        shader_texture_nodes = set()
        for material in materials:
            for node in material.node_tree.nodes:
                if (
                    isinstance(node, bpy.types.ShaderNodeTexImage)
                    and node.image
                ):
                    shader_texture_nodes.add(node)
        # Pack ShaderNodeTexImage images.
        for node in shader_texture_nodes:
            node.image.pack()

    @staticmethod
    def _get_loader_from_instance(instance):
        all_loaders = discover_loader_plugins()
        context = {
            "subset": {"schema": "openpype:container-2.0"},
            "version": {"data": {"families": [instance.data["family"]]}},
            "representation": {"name": "blend"},
        }
        loaders = loaders_from_repre_context(all_loaders, context)
        if loaders:
            return loaders[0]

    def process(self, instance):
        # Define extract output file path

        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.blend"
        filepath = os.path.join(stagingdir, filename)

        # Perform extraction
        self.log.info("Performing extraction..")

        plugin.deselect_all()

        data_blocks = set()
        objects = set()

        # Adding all members of the instance to data blocks that will be
        # written into the blender library.
        for member in instance:
            data_blocks.add(member)
            # Get reference from override library.
            if member.override_library and member.override_library.reference:
                data_blocks.add(member.override_library.reference)
            # Store objects to pack images from their materials.
            if isinstance(member, bpy.types.Object):
                objects.add(member)

        # Store instance metadata
        instance_collection = instance[-1]
        instance_metadata = instance_collection[AVALON_PROPERTY].to_dict()

        # Create ID to allow blender import without using OP tools
        repre_id = str(ObjectId())

        # Add container metadata to collection
        loader_module = self._get_loader_from_instance(instance)

        if not loader_module:
            raise RuntimeError(
                f"Loader module not found for instance: {instance.name}"
            )

        metadata_update(
            instance_collection,
            {
                "schema": "openpype:container-2.0",
                "id": AVALON_CONTAINER_ID,
                "name": instance.name,
                "namespace": instance.data.get("namespace", ""),
                "loader": loader_module.__name__,
                "representation": repre_id,
                "libpath": filepath,
                "asset_name": instance.name,
                "parent": str(instance.data["assetEntity"]["parent"]),
                "family": instance.data["family"],
            },
        )

        # Pack used images in the blend files.
        self._pack_images_from_objects(objects)

        bpy.ops.file.make_paths_absolute()
        bpy.data.libraries.write(filepath, data_blocks)

        # restor instance metadata
        instance_collection[AVALON_PROPERTY] = instance_metadata

        plugin.deselect_all()

        # Create representation dict
        representation = {
            "name": "blend",
            "ext": "blend",
            "files": filename,
            "stagingDir": stagingdir,
            "id": repre_id,
        }
        instance.data.setdefault("representations", [])
        instance.data["representations"].append(representation)

        self.log.info(
            f"Extracted instance '{instance.name}' to: {representation}"
        )
