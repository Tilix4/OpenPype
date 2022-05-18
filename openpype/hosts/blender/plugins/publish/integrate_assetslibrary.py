from collections import OrderedDict
from pprint import pprint

from bson.objectid import ObjectId
import pyblish.api
from openpype.hosts.blender.api import plugin
from openpype.hosts.blender.api.pipeline import metadata_update
import bpy
from bpy.types import Collection

from openpype.pipeline import legacy_io
from openpype.pipeline.constants import AVALON_CONTAINER_ID
from openpype.settings.lib import get_project_settings


class IntegrateAssetsLibrary(pyblish.api.InstancePlugin):
    """Connecting version level dependency links"""

    order = pyblish.api.IntegratorOrder + 0.3
    label = "Add to assets library"

    def process(self, instance):
        """Connect dependency links for all instances, globally
        TODO
        Code steps:
        * filter out instances that has "versionEntity" entry in data
        * find workfile instance within context
        * if workfile found:
            - link all `loadedVersions` as input of the workfile
            - link workfile as input of all publishing instances
        * else:
            - show "no workfile" warning
        * link instances' inputs if it's data has "inputVersions" entry
        * Write into database

        inputVersions:
            The "inputVersions" in instance.data should be a list of
            version document's Id (str or ObjectId), which are the
            dependencies of the publishing instance that should be
            extracted from working scene by the DCC specific publish
            plugin.

        """

        project_settings = get_project_settings(legacy_io.Session["AVALON_PROJECT"])
        blender_settings = project_settings.get("blender", {})

        if blender_settings.get("assets-library", {}).get("enabled"):
            # Mark as asset
            marked_as_assets = []
            # for instance in context:
            if True:
                asset = instance.data["name"]
                subset = instance.data["subset"]
                unique_number = plugin.get_unique_number(asset, subset)
                filename = f"{instance.name}.blend"
                libpath = f"/media/felix/T01/Projets/Normaal/pipeline/openpype_projects/Suzanna/AssetBrowser/{filename}"
                for obj in instance:
                    if isinstance(obj, Collection):
                        group_name = plugin.asset_name(asset, subset, unique_number)
                        print("toudou", pprint(instance.data))
                        metadata_update(
                            obj,
                            {
                                "schema": "openpype:container-2.0",
                                "id": AVALON_CONTAINER_ID,
                                "name": instance.name,
                                "namespace": instance.data["namespace"],
                                "loader": str(self.__class__.__name__),
                                "representation": str(
                                    [
                                        k
                                        for k, v in instance.data[
                                            "published_representations"
                                        ].items()
                                        if v["representation"]["name"] == "blend"
                                    ][0]
                                ),
                                "libpath": libpath,
                                "asset_name": instance.name,
                                "parent": str(instance.data["assetEntity"]["parent"]),
                                "family": instance.data["family"],
                                "objectName": group_name,
                            },
                        )
                        obj.asset_mark()
                        marked_as_assets.append(obj)

            # Save asset library
            bpy.ops.wm.save_as_mainfile(filepath=libpath, copy=True)

            # Unmark assets
            [b.asset_clear() for b in marked_as_assets]
