"""Load audio in Blender."""

from pathlib import Path
from typing import Dict, List, Set, Tuple

import bpy

from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.pipeline import metadata_update
from openpype.hosts.blender.api.properties import OpenpypeContainer
from openpype.pipeline.load.utils import get_representation_path


class AudioLoader(plugin.Loader):
    """Load audio in Blender."""

    families = ["audio"]
    representations = ["wav"]

    label = "Load Audio"
    icon = "volume-up"
    color = "orange"

    def load_library(
        self,
        libpath: Path,
        # container_name: str,
        **_kwargs
    ) -> Tuple[OpenpypeContainer, Set[bpy.types.ID]]:
        """OVERRIDE Load datablocks from blend file library.

        Args:
            libpath (Path): Path of library.
            container_name (str): Name of container to be loaded.
            container (OpenpypeContainer): Load into existing container.
                Defaults to None.

        Returns:
            Tuple[OpenpypeContainer, Set[bpy.types.ID]]:
                (Created scene container, Loaded datablocks)
        """

        # Append audio as sound in the sequence editor
        sound_seq = bpy.context.scene.sequence_editor.sequences.new_sound(
            libpath.stem,
            libpath.as_posix(),
            1,
            bpy.context.scene.frame_start,
        )

        # Keep audio sequence in the container
        metadata_update(
            sound_seq.sound,
            {
                "sequence_name": sound_seq.name,
            },
        )

        root_datablocks = {sound_seq.sound}
        return root_datablocks, root_datablocks | {sound_seq.sound}

    def update(self, container_metadata: Dict, representation: Dict) -> Tuple[OpenpypeContainer, List]:
        """OVERRIDE Update an existing container from a Blender scene."""
        return self.switch(container_metadata, representation)

    def switch(
        self, container_metadata: Dict, representation: Dict
    ) -> Tuple[OpenpypeContainer, List[bpy.types.ID]]:
        """OVERRIDE Simply change the sound filepath."""
        # Switch sound filepath
        container_datablock = bpy.data.sounds.get(container_metadata["objectName"])
        container_datablock.filepath = get_representation_path(representation)

        # Update metadata
        metadata_update(
            container_datablock,
            {
                "libpath": container_datablock.filepath,
                "representation": str(representation["_id"]),
            },
        )

        # Get datablocks
        datablocks = {container_datablock}
        if sound_seq := bpy.context.scene.sequence_editor.sequences.get(
            container_metadata["sequence_name"]
        ):
            datablocks.add(sound_seq)

        return container_datablock, datablocks

    def remove(self, container: Dict) -> bool:
        """OVERRIDE Remove an existing container from a Blender scene."""
        # Remove sequence if any
        if sound_seq := bpy.context.scene.sequence_editor.sequences.get(
            container["sequence_name"]
        ):
            bpy.context.scene.sequence_editor.sequences.remove(sound_seq)

        # Remove sound datablock
        bpy.data.sounds.remove(bpy.data.sounds.get(container["objectName"]))

        return super().remove(container)
