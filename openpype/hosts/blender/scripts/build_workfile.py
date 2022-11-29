import os
import bpy

from openpype.client import (
    get_asset_by_name,
    get_subset_by_name,
    get_last_version_by_subset_id,
    get_representations,
)
from openpype.lib import get_creator_by_name
from openpype.modules import ModulesManager
from openpype.pipeline import (
    legacy_io,
    legacy_create,
    discover_loader_plugins,
    load_container,
    loaders_from_representation,
)


def load_subset(
    project_name, asset_name, subset_name, loader_type=None, ext="blend"
):

    asset = get_asset_by_name(
        project_name,
        asset_name,
        fields=["_id"]
    )
    if not asset:
        return

    subset = get_subset_by_name(
        project_name,
        subset_name,
        asset["_id"],
        fields=["_id"],
    )
    if not subset:
        return

    last_version = get_last_version_by_subset_id(
        project_name,
        subset["_id"],
        fields=["_id"],
    )
    if not last_version:
        return

    representation = next(
        get_representations(
            project_name,
            version_ids=[last_version["_id"]],
            context_filters={"ext": [ext]},
        ),
        None
    )
    if not representation:
        return

    all_loaders = discover_loader_plugins(project_name=project_name)
    loaders = loaders_from_representation(all_loaders, representation)
    for loader in loaders:
        if loader_type and loader_type not in loader.__name__:
            continue
        return load_container(loader, representation)


def create_instance(creator_name, instance_name, **options):
    legacy_create(
        get_creator_by_name(creator_name),
        name=instance_name,
        asset=legacy_io.Session.get("AVALON_ASSET"),
        options=options,
    )


def load_casting(project_name, shot_name):

    modules_manager = ModulesManager()
    kitsu_module = modules_manager.modules_by_name.get("kitsu")
    if not kitsu_module or not kitsu_module.enabled:
        return

    import gazu

    gazu.client.set_host(os.environ["KITSU_SERVER"])
    gazu.log_in(os.environ["KITSU_LOGIN"], os.environ["KITSU_PWD"])

    shot_data = get_asset_by_name(project_name, shot_name, fields=["data"])

    shot = gazu.shot.get_shot(shot_data["data"]["zou"]["id"])
    casting = gazu.casting.get_shot_casting(shot)

    for actor in casting:
        for _ in range(actor["nb_occurences"]):
            load_subset(project_name, actor["asset_name"], "rigMain", "Link")

    gazu.log_out()


def build_workfile():
    project = legacy_io.Session["AVALON_PROJECT"]
    task = legacy_io.Session.get("AVALON_TASK").lower()
    asset = legacy_io.Session.get("AVALON_ASSET")

    if task in ("model", "modeling"):
        bpy.ops.mesh.primitive_cube_add()
        bpy.context.object.name = f"{asset}_model"
        bpy.context.object.data.name = f"{asset}_model"
        create_instance("CreateModel", "modelMain", useSelection=True)

    elif task in ("texture", "look", "lookdev", "shader"):
        create_instance("CreateLook", "lookMain")
        load_subset(project, asset, "modelMain", "Append")

    elif task in ("rig", "rigging"):
        bpy.ops.object.armature_add()
        bpy.context.object.name = f"{asset}_armature"
        bpy.context.object.data.name = f"{asset}_armature"
        create_instance("CreateRig", "rigMain", useSelection=True)
        load_subset(project, asset, "modelMain", "Append")

    elif task == "layout":
        create_instance("CreateLayout", "layoutMain")
        create_instance("CreateCamera", "cameraMain")
        create_instance("CreateReview", "reviewMain")
        load_subset(project, asset, "BoardReview", "Background", "mov")
        try:
            load_casting(project, asset)
        except RuntimeError:
            pass

    elif task in ("anim", "animation"):
        load_subset(project, asset, "layoutMain", "Append")
        load_subset(project, asset, "cameraMain", "Link")
        create_instance("CreateReview", "reviewMain")

    elif task in ("lighting", "light", "render", "rendering"):
        if not load_subset(project, asset, "layoutFromAnim", "Link"):
            load_subset(project, asset, "layoutMain", "Append")
        if not load_subset(project, asset, "cameraFromAnim", "Link"):
            load_subset(project, asset, "cameraMain", "Link")
        load_subset(project, asset, "animationMain", "Link")
    else:
        return False

    return True
