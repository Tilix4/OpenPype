"""Load an asset in Blender from an Alembic file."""

from openpype.hosts.blender.api import plugin


class CacheModelLoader(plugin.AssetLoader):
    """Import cache models.

    Stores the imported asset in a collection named after the asset.

    Note:
        At least for now it only supports Alembic files.
    """

    families = ["model", "pointcache"]
    representations = ["abc"]

    label = "Import Alembic"
    icon = "download"
    color = "orange"
    order = 4

    load_type = "ABC"
