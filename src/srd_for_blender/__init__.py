# The MIT License (MIT)
#
# Copyright 2023 Sony Corporation
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import enum
import os
import subprocess
import sys
import time

# append lib directories
SCRIPT_DIR = os.path.dirname(__file__)
LIB_DIR = os.path.join(SCRIPT_DIR, "lib")
os.makedirs(LIB_DIR, exist_ok=True)
sys.path += [SCRIPT_DIR, LIB_DIR]

try:
    import flatbuffers
except ImportError:
    from pip._internal import main as _main

    _main(["install", "flatbuffers", "-t", os.path.join(os.path.dirname(__file__), "lib")])
    try:
        import flatbuffers
    except ImportError:
        raise "flatbuffers install failed."

try:
    import pynng
except ImportError:
    from pip._internal import main as _main

    _main(["install", "pynng", "-t", os.path.join(os.path.dirname(__file__), "lib")])
    try:
        import pynng
    except ImportError:
        raise "pynng install failed."

import bpy
import utils.CheckModal as CheckModal
from IPCViewerCommand import CommandSender
from SRDViewer import srdViewer

bl_info = {
    "name": "Spatial Reality Display",
    "author": "Sony Corporation",
    "version": (1, 0, 0),
    "blender": (3, 3, 0),
    "description": "SpatialRealityDisplayPlugin for Blender",
    "warning": "",
    "support": "COMMUNITY",
    # "doc_url": "https://",
    # "tracker_url": "https://",
    "category": "3D Viewer",
}


# region classes
class SRDPropertyIndex(enum.IntEnum):
    VisibleGizmo = enum.auto()
    SyncTransform = enum.auto()
    SyncAnimationFrame = enum.auto()
    SyncEditMesh = enum.auto()
    SpatialClippingSetting = enum.auto()
    ClipPlaneFront = enum.auto()
    ClipPlaneTop = enum.auto()


class SRDPropertyGroup(bpy.types.PropertyGroup):
    VisibleGizmo: bpy.props.BoolProperty(
        name="",
        description="",
        default=True,
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.VisibleGizmo
        ),
    )
    SyncTransform: bpy.props.BoolProperty(
        name="",
        description="",
        default=True,
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.SyncTransform
        ),
    )
    SyncAnimationFrame: bpy.props.BoolProperty(
        name="",
        description="",
        default=False,
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.SyncAnimationFrame
        ),
    )
    SyncEditMesh: bpy.props.BoolProperty(
        name="",
        description="",
        default=False,
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.SyncEditMesh
        ),
    )
    SpatialClippingSetting: bpy.props.EnumProperty(
        name="",
        description="",
        items=[
            ("1", "No Clip", "Description..."),
            ("2", "Clip(100%)", "Some other description"),
            ("3", "Clip(150%)", "Some other description"),
        ],
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.SpatialClippingSetting
        ),
    )
    ClipPlaneFront: bpy.props.BoolProperty(
        name="",
        description="",
        default=True,
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.ClipPlaneFront
        ),
    )
    ClipPlaneTop: bpy.props.BoolProperty(
        name="",
        description="",
        default=True,
        update=lambda self, context: change_property_callback(
            self, context, SRDPropertyIndex.ClipPlaneTop
        ),
    )


class SRD_OT_Create(bpy.types.Operator):
    bl_idname = "object.srd_opt_create"
    bl_label = "NOP"

    def execute(self, context):
        srdViewer.m_sourceOperator = self
        srdViewer.createGizmoCamera()
        # force redraw tip
        if bpy.ops.object.select_all.poll():
            bpy.ops.object.select_all(action="DESELECT")
            for o in bpy.context.scene.collection.objects:
                if o.get("gizmoForSpatialRealityDisplayNode"):
                    o.select_set(True)
                    break
        srdViewer.m_sourceOperator = None
        return {"FINISHED"}


class SRD_OT_LoadScene(bpy.types.Operator):
    bl_idname = "object.srd_opt_load_scene"
    bl_label = "LoadScene"

    @classmethod
    def poll(cls, context):
        return (
            srdViewer.m_viewerStatus == srdViewer.ProcessStatus.CLOSED
            or srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING
        )

    def execute(self, context):
        srdViewer.m_sourceOperator = self
        srdViewer.startViewer()
        srdViewer.m_sourceOperator = None
        return {"FINISHED"}

    def invoke(self, context, event):
        tri_count = 0
        for i in [i for i in bpy.context.scene.objects if i.type == "MESH"]:
            i.data.calc_loop_triangles()
            tri_count += len(i.data.loop_triangles)
        if tri_count > 10**6:
            return context.window_manager.invoke_props_dialog(self, width=350)
        else:
            return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.label(text="The mesh is currently too dense and may take a long time to display.")


class SRD_OT_Shutdown(bpy.types.Operator):
    bl_idname = "object.srd_opt_shutdown"
    bl_label = "NOP"

    @classmethod
    def poll(cls, context):
        return srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING

    def execute(self, context):
        srdViewer.m_sourceOperator = self
        srdViewer.shutdownSRDViewer()
        srdViewer.m_sourceOperator = None
        return {"FINISHED"}


class SRD_OT_Start(bpy.types.Operator):
    bl_idname = "object.srd_opt_start"
    bl_label = "NOP"

    def execute(self, context):
        srdViewer.m_sourceOperator = self
        srdViewer.startAnim()
        srdViewer.m_sourceOperator = None
        return {"FINISHED"}


class SRD_OT_Setframe(bpy.types.Operator):
    bl_idname = "object.srd_opt_setframe"
    bl_label = "NOP"

    def execute(self, context):
        srdViewer.m_sourceOperator = self
        srdViewer.setAnimFrame()
        srdViewer.m_sourceOperator = None
        return {"FINISHED"}


class SRD_OT_Stop(bpy.types.Operator):
    bl_idname = "object.srd_opt_stop"
    bl_label = "NOP"

    def execute(self, context):
        srdViewer.m_sourceOperator = self
        srdViewer.stopAnim()
        srdViewer.m_sourceOperator = None
        return {"FINISHED"}


class SRD_PT_Panel(bpy.types.Panel):
    bl_label = "Spatial Reality Display Control Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "SRDViewer"
    bl_context = ""

    def draw_header(self, context):
        layout = self.layout
        # layout.label(text="", icon='PLUGIN')

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        prop = bpy.context.window_manager.srd_prop_grp

        # camera
        column = layout.column(align=True)
        column.label(text="Camera", translate=False)
        row = column.row(align=True)
        row.operator(SRD_OT_Create.bl_idname, text="create")
        row.prop(prop, "VisibleGizmo", text="Visible GIZMO")
        column.separator()

        # viewer
        column.label(text="Viewer", translate=False)
        row = column.row(align=True)
        row.operator(SRD_OT_LoadScene.bl_idname, text="load scene")
        row.operator(SRD_OT_Shutdown.bl_idname, text="shutdown")
        column.separator()

        # animation
        column.label(text="Animation", translate=False)
        row = column.row(align=True)
        row.operator(SRD_OT_Start.bl_idname, text="start")
        row.operator(SRD_OT_Stop.bl_idname, text="stop")
        row.operator(SRD_OT_Setframe.bl_idname, text="set frame")
        column.separator()

        # sync setting
        column.label(text="Sync Setting")
        row = column.row(align=True)
        row.prop(prop, "SyncTransform", text="Transform", translate=False)
        row.prop(prop, "SyncAnimationFrame", text="Animation frame")
        column.separator()

        # spatial clipping
        column.label(text="Spatial Clipping")
        row = column.row(align=True)
        row.label(text="Settings:")
        row.prop(prop, "SpatialClippingSetting", expand=True, text="dummy")
        row = column.row(align=True)
        row.label(text="Clip Plane:")
        row.prop(prop, "ClipPlaneFront", text="Front", translate=False)
        row.prop(prop, "ClipPlaneTop", text="Top", translate=False)
        column.separator()


classes = [
    SRD_PT_Panel,
    SRD_OT_Create,
    SRD_OT_LoadScene,
    SRD_OT_Shutdown,
    SRD_OT_Start,
    SRD_OT_Setframe,
    SRD_OT_Stop,
    SRDPropertyGroup,
]
# endregion


def change_property_callback(self, context, index: SRDPropertyIndex):
    data: SRDPropertyGroup = bpy.context.window_manager.srd_prop_grp
    if index == SRDPropertyIndex.VisibleGizmo:
        visible = data.VisibleGizmo
        srdViewer.setGizmoVisibleState(visible)
    if (
        index == SRDPropertyIndex.SyncTransform
        or index == SRDPropertyIndex.SyncAnimationFrame
        or index == SRDPropertyIndex.SyncEditMesh
    ):
        transformFlag = data.SyncTransform
        animationFlag = data.SyncAnimationFrame
        editModelFlag = data.SyncEditMesh
        srdViewer.syncSettings(transformFlag, animationFlag, editModelFlag)
    if index == SRDPropertyIndex.SpatialClippingSetting:
        retVal = int(data.SpatialClippingSetting)
        srdViewer.setClippingMethod(retVal)
    if index == SRDPropertyIndex.ClipPlaneFront or index == SRDPropertyIndex.ClipPlaneTop:
        front = data.ClipPlaneFront
        top = data.ClipPlaneTop
        srdViewer.setClippingPlane(front, top)


def init_props():
    scene = bpy.types.Scene

    scene.srd_prop_log = bpy.props.StringProperty(
        name="",
        description="",
        default="",
        maxlen=1024,
        subtype="NONE",
    )  # ログはシーンに保存する?

    bpy.types.WindowManager.srd_prop_grp = bpy.props.PointerProperty(type=SRDPropertyGroup)


def clear_props():
    scene = bpy.types.Scene
    del scene.srd_prop_log
    del bpy.types.WindowManager.srd_prop_grp


def register():
    initializePlugin(bpy.context)
    for cls in classes:
        bpy.utils.register_class(cls)
    init_props()
    CheckModal.init_structs()


def unregister():
    clear_props()
    for cls in classes:
        bpy.utils.unregister_class(cls)
    uninitializePlugin(bpy.context)
    bpy.app.translations.unregister(__name__)


def initializePlugin(context):
    # 50 msec 監視
    srdViewer.fViewerWatchTimerCallbackId = bpy.app.timers.register(
        srdViewer.updateViewerStatusTimerCB
    )

    srdViewer.fUpdateGizmoCallbackId = bpy.app.handlers.depsgraph_update_pre.append(
        srdViewer.updateGizmo
    )

    srdViewer.fSyncTransformCallbackId = bpy.app.handlers.depsgraph_update_post.append(
        srdViewer.checkTransformCB
    )

    # 100 msec 監視
    srdViewer.fElapsedTimeCallbackId = bpy.app.timers.register(srdViewer.updateTransformTimerCB)

    # Ver0.8 追加部
    srdViewer.fTimeChangeCallbackId = bpy.app.handlers.frame_change_pre.append(
        srdViewer.updateAnimationFrameCB
    )

    srdViewer.fLoadPostHandlerId = bpy.app.handlers.load_post.append(srdViewer.loadPostHandler)

    srdViewer.m_messageSender = CommandSender("ipc://srdViewer")

    srdViewer.m_synchronize = True
    srdViewer.m_syncTransform = True  # transform のデフォルトのみ True
    srdViewer.m_syncAnimation = False
    srdViewer.m_syncEditModel = False
    srdViewer.m_needReload = False
    srdViewer.m_loading = False

    ct = time.time()
    srdViewer.m_attrChangeTimeStamp = ct
    srdViewer.m_deleteFbxFileCheckTimeStamp = ct
    srdViewer.m_deleteRequest = False
    srdViewer.m_viewerStatus = srdViewer.ProcessStatus.CLOSED
    srdViewer.m_clippingPlane = srdViewer.ClippingPlane.BOTH
    srdViewer.m_clippingMethod = srdViewer.ClippingMethod.NONE

    srdViewer.setExecutablePath()
    srdViewer.setFbxPath()
    srdViewer.setUniqueFbxFileName()

    srdViewer.m_si = subprocess.STARTUPINFO()
    srdViewer.m_pi = None


def uninitializePlugin(context):
    # コールバックの終了
    srdViewer.shutdownSRDViewer()
    srdViewer.removeCallbacks()

    # fbx が残っている場合の消去
    srdViewer.removeFbxFile()

    if srdViewer.m_messageSender:
        srdViewer.m_messageSender.Stop()
        srdViewer.m_messageSender = None


if __name__ == "__main__":
    register()
