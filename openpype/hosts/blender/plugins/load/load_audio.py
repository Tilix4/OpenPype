"""Load audio in Blender."""

from pathlib import Path
from typing import Dict, List, Set, Tuple

import bpy

from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.pipeline import metadata_update
from openpype.hosts.blender.api.properties import OpenpypeContainer
<<<<<<< Updated upstream
from openpype.hosts.blender.api.utils import AVALON_PROPERTY
=======
from openpype.pipeline.load.utils import get_representation_path
>>>>>>> Stashed changes


class AudioLoader(plugin.Loader):
    """Load audio in Blender."""

    families = ["audio"]
    representations = ["wav"]

    label = "Load Audio"
    icon = "volume-up"
    color = "orange"

    def load_library_as_container(
        self,
        libpath: Path,
        container_name: str,
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
            container_name,
            libpath.as_posix(),
            1,
            bpy.context.scene.frame_start,
        )

        # Put into a container
        container_datablock = sound_seq.sound
        container_datablock.name = container_name
        datablocks = {container_datablock, sound_seq.sound}

        # Keep audio sequence in the container
        metadata_update(
            container_datablock,
            {
                "sequence_name": sound_seq.name,
            },
        )
        
        return container_datablock, datablocks

<<<<<<< Updated upstream
    def load(self, *args, **kwargs):
        """OVERRIDE.

        Keep container metadata in sound datablock to allow container
        auto creation of theses datablocks.
        """
        container, datablocks = super().load(*args, **kwargs)

        # Set container metadata to sound datablock
        datablocks[0][AVALON_PROPERTY] = container.get(AVALON_PROPERTY)

        return container, datablocks

    def update(
        self, *args, **kwargs
    ) -> Tuple[OpenpypeContainer, List[bpy.types.ID]]:
=======
    def update(self, container_metadata: Dict, representation: Dict) -> Tuple[OpenpypeContainer, List]:
>>>>>>> Stashed changes
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

<<<<<<< Updated upstream
        # Set container metadata to sound datablock
        sound = datablocks[0]
        sound[AVALON_PROPERTY] = container.get(AVALON_PROPERTY)

        return container, datablocks
=======
        # Get datablocks
        datablocks = {container_datablock}
        if sound_seq := bpy.context.scene.sequence_editor.sequences.get(
            container_metadata["sequence_name"]
        ):
            datablocks.add(sound_seq)

        return container_datablock, datablocks
>>>>>>> Stashed changes

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
