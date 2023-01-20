import os
from typing import Set
import bpy

from openpype.client import (
    get_asset_by_name,
    get_subset_by_name,
    get_last_version_by_subset_id,
    get_representations,
)
from openpype.hosts.blender.api.properties import OpenpypeContainer
from openpype.modules import ModulesManager
from openpype.pipeline import (
    legacy_io,
    legacy_create,
    discover_loader_plugins,
    load_container,
    loaders_from_representation,
)
from openpype.pipeline.create import get_legacy_creator_by_name


def load_subset(
    project_name, asset_name, subset_name, loader_type=None, ext="blend"
):
    """Load the representation of the last version of subset.

    Args:
        project_name (str): The project name.
        asset_name (str): The asset name.
        subset_name (str): The subset name.
        loader_type (str, optional): The loader name. Defaults to None.
        ext (str, optional): The representation extension. Defaults to "blend".

    Returns:
        The return of the `load_container()` function.
    """

    asset = get_asset_by_name(project_name, asset_name, fields=["_id"])
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
        None,
    )
    if not representation:
        return

    all_loaders = discover_loader_plugins(project_name=project_name)
    loaders = loaders_from_representation(all_loaders, representation)
    for loader in loaders:
        if loader_type == loader.load_type:
            return load_container(loader, representation)


def create_instance(creator_name, instance_name, **options):
    """Create openpype publishable instance."""
    return legacy_create(
        get_legacy_creator_by_name(creator_name),
        name=instance_name,
        asset=legacy_io.Session.get("AVALON_ASSET"),
        options=options,
    )


def load_casting(project_name, shot_name) -> Set[OpenpypeContainer]:
    """Load casting from shot_name using kitsu api."""

    modules_manager = ModulesManager()
    kitsu_module = modules_manager.modules_by_name.get("kitsu")
    if not kitsu_module or not kitsu_module.enabled:
        return

    import gazu

    gazu.client.set_host(os.environ["KITSU_SERVER"])
    gazu.log_in(os.environ["KITSU_LOGIN"], os.environ["KITSU_PWD"])

    shot_data = get_asset_by_name(project_name, shot_name, fields=["data"])[
        "data"
    ]

    shot = gazu.shot.get_shot(shot_data["zou"]["id"])
    casting = gazu.casting.get_shot_casting(shot)

    containers = set()
    for actor in casting:
        for _ in range(actor["nb_occurences"]):
            if actor["asset_type_name"] == "Environment":
                subset_name = "setdressMain"
            else:
                subset_name = "rigMain"
            container, _datablocks = load_subset(
                project_name, actor["asset_name"], subset_name, "LINK"
            )
            containers.add(container)

    gazu.log_out()

    return containers


def build_model(asset_name):
    """Build model workfile.

    Args:
        asset_name (str): The current asset name from OpenPype Session.
    """
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.object.name = f"{asset_name}_model"
    bpy.context.object.data.name = f"{asset_name}_model"
    create_instance("CreateModel", "modelMain", useSelection=True)


def build_look(project_name, asset_name):
    """Build look workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """
    create_instance("CreateLook", "lookMain")
    load_subset(project_name, asset_name, "modelMain", "APPEND")


def build_rig(project_name, asset_name):
    """Build rig workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """
    bpy.ops.object.armature_add()
    bpy.context.object.name = f"{asset_name}_armature"
    bpy.context.object.data.name = f"{asset_name}_armature"
    create_instance("CreateRig", "rigMain", useSelection=True)
    load_subset(project_name, asset_name, "modelMain", "APPEND")


def build_layout(project_name, asset_name):
    """Build layout workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """

    layout_instance = create_instance("CreateLayout", "layoutMain")

    # Load casting from kitsu breakdown.
    try:
        containers = load_casting(project_name, asset_name)

        # Link loaded containers to layout collection
        for c in containers:
            layout_instance.datablock_refs[0].datablock.children.link(
                c.outliner_entity
            )
            bpy.context.scene.collection.children.unlink(c.outliner_entity)
    except RuntimeError:
        containers = {}

    # Try to load camera from environment's setdress
    try:
        # Get env asset name
        env_asset_name = next(
            (
                c["avalon"]["asset_name"]
                for c in containers
                if c.get("avalon", {}).get("family") == "setdress"
            ),
            None,
        )
        if env_asset_name:
            # Load camera published at environment task
            cam_container, _cam_datablocks = load_subset(
                project_name, env_asset_name, "cameraMain", "APPEND"
            )

            # Select camera
            main_camera = next(
                d_ref.datablock
                for d_ref in cam_container.datablock_refs
                if hasattr(d_ref.datablock, "type")
                and d_ref.datablock.type == "CAMERA"
            )
            main_camera.select_set(True)

            # Remove camera container to make it publishable
            # TODO replace by make_container_publishable when fixed
            openpype_containers = bpy.context.scene.openpype_containers
            openpype_containers.remove(
                openpype_containers.find(cam_container.name)
            )
    except RuntimeError:
        main_camera = None

    # Create camera instance from loaded camera
    cam_instance = create_instance(
        "CreateCamera", "cameraMain", useSelection=True
    )

    # Select camera from cameraMain instance to link with the review
    main_camera.name = cam_instance.name
    main_camera.data.name = cam_instance.name

    # Create review instance with camera instance's camera object
    review_instance = create_instance("CreateReview", "reviewMain")
    # TODO dirty as hell, instance creation must be done using the operators to avoid this
    review_instance.datablock_refs[0].datablock.objects.unlink(
        review_instance.datablock_refs[0].datablock.objects[0]
    )
    review_instance.datablock_refs[0].datablock.objects.link(main_camera)

    # load the board mov as image background linked into the camera.
    # TODO when fixed
    # load_subset(project_name, asset_name, "BoardReview", "Background", "mov")


def build_anim(project_name, asset_name):
    """Build anim workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """

    load_subset(project_name, asset_name, "layoutMain", "APPEND")
    load_subset(project_name, asset_name, "cameraMain", "LINK")

    # Get animation instance creator
    Creator = get_legacy_creator_by_name("CreateAnimation")
    if not Creator:
        raise ValueError('Creator plugin "CreateAnimation" was not found.')

    # TODO shouldn't touch the selection
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        # Select camera from cameraMain instance to link with the review.
        # TODO shouldn't touch the selection
        if obj.type == "CAMERA":
            obj.select_set(True)
            break
        elif obj.type == "ARMATURE":
            # Create animation instance
            variant_name = obj.name.capitalize()
            plugin = Creator(
                f"animation{variant_name}",
                asset_name,
                {"variant": variant_name},
            )
            plugin.process([obj])
            # instance = plugin.process([obj])
            # instance.name = f"{instance.name}:{obj.name}"

    create_instance("CreateReview", "reviewMain", useSelection=True)


def build_render(project_name, asset_name):
    """Build render workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """

    if not load_subset(project_name, asset_name, "layoutFromAnim", "LINK"):
        load_subset(project_name, asset_name, "layoutMain", "APPEND")
    if not load_subset(project_name, asset_name, "cameraFromAnim", "LINK"):
        load_subset(project_name, asset_name, "cameraMain", "LINK")
    load_subset(project_name, asset_name, "animationMain", "LINK")


def build_workfile():
    """build first workfile Main function."""
    project_name = legacy_io.Session["AVALON_PROJECT"]
    asset_name = legacy_io.Session.get("AVALON_ASSET")
    task_name = legacy_io.Session.get("AVALON_TASK").lower()

    if task_name in ("model", "modeling", "fabrication"):
        build_model(asset_name)

    elif task_name in ("texture", "look", "lookdev", "shader"):
        build_look(project_name, asset_name)

    elif task_name in ("rig", "rigging"):
        build_rig(project_name, asset_name)

    elif task_name == "layout":
        build_layout(project_name, asset_name)

    elif task_name in ("anim", "animation"):
        build_anim(project_name, asset_name)

    elif task_name in ("lighting", "light", "render", "rendering"):
        build_render(project_name, asset_name)

    else:
        return False

    return True


if __name__ == "__main__":
    build_workfile()
