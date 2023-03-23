import os
from time import sleep
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
        if loader_type in loader.__name__:
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

    containers = []
    for actor in casting:
        for _ in range(actor["nb_occurences"]):
            if actor["asset_type_name"] == "Environment":
                subset_name = "setdressMain"
                loader_name = "LinkSetdressLoader"
            else:
                subset_name = "rigMain"
                loader_name = "LinkRigLoader"
            try:
                container, _datablocks = load_subset(
                    project_name, actor["asset_name"], subset_name, loader_name
                )
                containers.append(container)
                sleep(1)  # TODO blender is too fast for windows
            except TypeError:
                print(f"Cannot load {actor['asset_name']} {subset_name}.")

    gazu.log_out()

    return containers


def build_model(project_name, asset_name):
    """Build model workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str): The current asset name from OpenPype Session.
    """
    bpy.ops.mesh.primitive_cube_add()
    bpy.context.object.name = f"{asset_name}_model"
    bpy.context.object.data.name = f"{asset_name}_model"
    create_instance("CreateModel", "modelMain", useSelection=True)
    # load the concept reference as image reference in the scene.
    load_subset(
        project_name, asset_name, "ConceptReference", "Reference", "jpg"
    )


def build_look(project_name, asset_name):
    """Build look workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """
    create_instance("CreateLook", "lookMain")
    load_subset(project_name, asset_name, "modelMain", "AppendModelLoader")


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
    load_subset(project_name, asset_name, "modelMain", "AppendModelLoader")


def create_gdeformer_collection(parent_collection: bpy.types.Collection):
    """Create GDEFORMER collection under a parent collection.

    Args:
        parent_collection (bpy.types.Collection): Collection to create GDEFORMER col in
    """
    # Create GDEFORMER collection
    gdeformer_col = bpy.data.collections.new("GDEFORMER")
    parent_collection.children.link(gdeformer_col)
    for obj in bpy.context.scene.collection.all_objects:
        if obj.name.startswith("GDEFORM"):
            gdeformer_col.objects.link(obj)

        # Assign collection to sol(s) object(s)
        if obj.name.startswith("sol"):
            if obj.modifiers.get("GroundDeform"):
                obj.modifiers["GroundDeform"]["Input_2"] = gdeformer_col


def build_layout(project_name, asset_name):
    """Build layout workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """

    layout_instance = create_instance("CreateLayout", "layoutMain")

    # Load casting from kitsu breakdown.
    try:
        load_casting(project_name, asset_name)

        # NOTE cannot rely on containers from load_casting, memory is shuffled
        containers = bpy.context.scene.openpype_containers

        # Link loaded containers to layout collection
        for c in containers:
            layout_instance.datablock_refs[0].datablock.children.link(
                c.outliner_entity
            )
            bpy.context.scene.collection.children.unlink(c.outliner_entity)

        # Create GDEFORMER collection
        create_gdeformer_collection(
            layout_instance.datablock_refs[0].datablock
        )
    except RuntimeError:
        containers = {}

    # Try to load camera from environment's setdress
    camera_collection = None
    env_asset_name = None
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
                project_name,
                env_asset_name,
                "cameraMain",
                "AppendCameraLoader",
            )

            # Make cam container publishable
            bpy.ops.scene.make_container_publishable(
                container_name=cam_container.name,
                convert_to_current_asset=True,
            )

            # Keep camera collection
            camera_collection = (
                bpy.context.scene.openpype_instances[-1]
                .datablock_refs[0]
                .datablock
            )
    except RuntimeError:
        camera_collection = None

    # Ensure camera instance
    if not camera_collection:
        bpy.ops.scene.create_openpype_instance(
            creator_name="CreateCamera",
            asset_name=asset_name,
            subset_name="cameraMain",
            gather_into_collection=True,
        )
        camera_collection = (
            bpy.context.scene.openpype_instances[-1]
            .datablock_refs[0]
            .datablock
        )

    # Create review instance with camera collection
    bpy.ops.scene.create_openpype_instance(
        creator_name="CreateReview",
        asset_name=asset_name,
        subset_name="reviewMain",
        datapath="collections",
        datablock_name=camera_collection.name,
    )

    # load the board mov as image background linked into the camera
    load_subset(
        project_name, asset_name, "BoardReference", "Background", "mov"
    )

    # Delete sound sequence from board mov
    sound_seq = bpy.context.scene.sequence_editor.sequences[-1]
    if sound_seq:
        bpy.context.scene.sequence_editor.sequences.remove(sound_seq)

    # load the audio reference as sound into sequencer
    load_subset(project_name, asset_name, "AudioReference", "Audio", "wav")

    # load the concept reference of the environment as image background.
    if env_asset_name:
        load_subset(
            project_name,
            env_asset_name,
            "ConceptReference",
            "Background",
            "jpg",
        )

    # Setup cryptomatte
    bpy.context.scene.view_layers[
        "ViewLayer"
    ].use_pass_cryptomatte_asset = True

    # Load base nodegroup and make it publishable
    _compo_container, compo_datablocks = load_subset(
        project_name,
        "CompositingNodesBank",
        "nodegroupMatteColorCorrect",
        "Append",
    )

    input_image_node = None
    for container in containers:
        if container.get("avalon", {}).get("family") == "rig":
            input_image_node = setup_character_compositing(
                asset_name,
                container.name,
                list(compo_datablocks)[0],
                input_image_node,
            )
    else:
        # Link last matte color correct node to composite node
        composite_node = bpy.context.scene.node_tree.nodes["Composite"]
        bpy.context.scene.node_tree.links.new(
            input_image_node.outputs["Image"],
            composite_node.inputs["Image"],
        )


def setup_character_compositing(
    asset_name, character_name, source_compositing_nodegroup, input_image_node
) -> bpy.types.NodeTree:
    """Setup compositing nodes for character.

    Args:
        asset_name (str):  The current asset name from OpenPype Session.
        character_name (str):  The character to create compositing of.
        source_compositing_nodegroup (bpy.types.NodeTree):  The source nodegroup to use for compositing.
        input_image_node (bpy.types.Node):  The input image node to use for compositing.

    Returns:
        bpy.types.NodeTree:  The output image node.
    """
    scene = bpy.context.scene
    scene.use_nodes = True

    # Get render layers node
    render_layer_node = scene.node_tree.nodes.get("Render Layers")

    # Set render layers node as input image node if not already set
    if not input_image_node:
        input_image_node = scene.node_tree.nodes["Render Layers"]

    # Create crypto node for character
    crypto_node = scene.node_tree.nodes.new("CompositorNodeCryptomatteV2")
    crypto_node.name = f"{character_name}_Cryptomatte"

    # Link render layers to crypto node
    scene.node_tree.links.new(
        render_layer_node.outputs["Image"],
        crypto_node.inputs["Image"],
    )

    # Set matte id by rig name
    rig_name = None
    for obj in bpy.data.collections[character_name].all_objects:
        if obj.type == "ARMATURE":
            rig_name = obj.name
            break

    # If no rig found, print error and skip
    if not rig_name:
        print(f"Could not find rig for {character_name}")
        return

    crypto_node.matte_id = rig_name

    # Create matte color correct node
    matte_color_correct_node = scene.node_tree.nodes.new("CompositorNodeGroup")
    matte_color_correct_node.name = f"{character_name}_MatteColorCorrect"
    compositing_nodegroup = source_compositing_nodegroup.copy()
    compositing_nodegroup.name = f"{character_name}_Compositing"
    matte_color_correct_node.node_tree = compositing_nodegroup

    # Link crypto node to matte color correct node
    scene.node_tree.links.new(
        crypto_node.outputs["Matte"],
        matte_color_correct_node.inputs["Matte"],
    )

    # Link input image node to matte color correct node
    scene.node_tree.links.new(
        input_image_node.outputs["Image"],
        matte_color_correct_node.inputs["Image"],
    )

    # Create instance for compositing node
    bpy.ops.scene.create_openpype_instance(
        creator_name="CreateBlenderNodegroup",
        asset_name=asset_name,
        subset_name=f"nodegroupCompositing{character_name}",
        datapath="node_groups",
        datablock_name=compositing_nodegroup.name,
    )

    return matte_color_correct_node


def build_anim(project_name, asset_name):
    """Build anim workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """
    layout_container, _layout_datablocks = load_subset(
        project_name, asset_name, "layoutMain", "LinkLayoutLoader"
    )

    # Make container publishable, expose its content
    layout_collection_name = layout_container.outliner_entity.name
    bpy.ops.scene.make_container_publishable(
        container_name=layout_container.name
    )

    # Substitute overridden GDEFORMER collection by local one
    old_gdeform_collection = bpy.data.collections.get("GDEFORMER")
    if old_gdeform_collection:
        old_gdeform_collection.name += ".old"
        layout_collection = bpy.data.collections.get(layout_collection_name)
        create_gdeformer_collection(layout_collection)
        bpy.data.collections.remove(old_gdeform_collection)

    # Load camera
    cam_container, _cam_datablocks = load_subset(
        project_name, asset_name, "cameraMain", "AppendCameraLoader"
    )

    # Clean cam container from review collection
    # NOTE meant to be removed ASAP
    for i, d_ref in reversed(list(enumerate(cam_container.datablock_refs))):
        if isinstance(
            d_ref.datablock, bpy.types.Collection
        ) and d_ref.datablock.name.endswith("reviewMain"):
            bpy.data.collections.remove(d_ref.datablock)
            cam_container.datablock_refs.remove(i)

    # Get main camera
    camera_collection = next(
        (
            d_ref.datablock
            for d_ref in cam_container.datablock_refs
            if isinstance(d_ref.datablock, bpy.types.Collection)
        ),
        None,
    )

    # Make cam container publishable
    bpy.ops.scene.make_container_publishable(container_name=cam_container.name)

    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            # Create animation instance
            variant_name = obj.name[obj.name.find("RIG_") + 4 :].capitalize()
            bpy.ops.scene.create_openpype_instance(
                creator_name="CreateAnimation",
                asset_name=asset_name,
                subset_name=f"animation{variant_name}",
                datapath="objects",
                datablock_name=obj.name,
                use_selection=False,
            )

    # Create review
    bpy.ops.scene.create_openpype_instance(
        creator_name="CreateReview",
        asset_name=asset_name,
        subset_name="reviewMain",
        datapath="collections",
        datablock_name=camera_collection.name,
        use_selection=False,
    )

    # load the board mov as image background linked into the camera
    load_subset(
        project_name, asset_name, "BoardReference", "Background", "mov"
    )


def build_render(project_name, asset_name):
    """Build render workfile.

    Args:
        project_name (str):  The current project name from OpenPype Session.
        asset_name (str):  The current asset name from OpenPype Session.
    """

    load_subset(project_name, asset_name, "layoutMain", "AppendLayoutLoader")
    load_subset(project_name, asset_name, "cameraMain", "LinkCameraLoader")

    # TODO : Because subset animationMain no longer be used,
    # we need to load all animation subsets from the asset.
    _anim_container, anim_datablocks = load_subset(
        project_name, asset_name, "animationMain", "LinkAnimationLoader"
    )

    # Try to assign linked actions by parsing their name
    for action in anim_datablocks:
        users = action.get("users", {})
        for user_name in users:
            obj = bpy.context.scene.objects.get(user_name)
            if obj:
                # Ensure animation data
                if not obj.animation_data:
                    obj.animation_data_create()

                # Assign action
                obj.animation_data.action = action
            else:
                print(
                    f"Cannot match armature by name '{user_name}' "
                    f"for action: {action.name}"
                )
                continue


def build_workfile():
    """build first workfile Main function."""
    project_name = legacy_io.Session["AVALON_PROJECT"]
    asset_name = legacy_io.Session.get("AVALON_ASSET")
    task_name = legacy_io.Session.get("AVALON_TASK").lower()

    if task_name in ("model", "modeling", "fabrication"):
        build_model(project_name, asset_name)

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

    # Auto save
    if bpy.data.filepath:
        bpy.ops.wm.save_mainfile()

    return True


if __name__ == "__main__":
    build_workfile()
