"""Load a setdress in Blender."""

from openpype.hosts.blender.api import plugin


class LinkSetdressLoader(plugin.BlendLoader):
    """Link setdress from a .blend file."""

    families = ["setdress"]
    representations = ["blend"]

    label = "Link SetDress"
    icon = "link"
    color = "orange"
    order = 0

    load_type = "LINK"


<<<<<<< Updated upstream
class AppendSetdressLoader(plugin.BlendLibraryLoader):
=======
class AppendSetdressLoader(plugin.BlendLoader):
>>>>>>> Stashed changes
    """Append setdress from a .blend file."""

    families = ["setdress"]
    representations = ["blend"]

    label = "Append SetDress"
    icon = "paperclip"
    color = "orange"
    order = 1

    load_type = "APPEND"
