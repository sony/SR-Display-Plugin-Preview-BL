import ctypes
import datetime
import enum
import inspect
import os
import random
import subprocess
import time
import typing
from math import radians

import bpy
import IPC
import mathutils
import utils.CheckModal as CheckModal
import Viewer
from IPCViewerCommand import CommandSender

WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
WAIT_FAILED = 0xFFFFFFFF


class srdViewer:
    # region プラグインで管理するコールバック関連
    # Attribute Change / Timer(100msec) / timeChangeコールバックとアトリビュートチェック関数
    def updateViewerStatusTimerCB() -> float:
        period = 0.05
        if srdViewer.m_pi is None or srdViewer.m_pi.poll() is not None:
            srdViewer.m_pi = None
            srdViewer.m_pHandle = None
            srdViewer.m_viewerStatus = srdViewer.ProcessStatus.CLOSED
            if srdViewer.m_messageSender.IsStarted():
                srdViewer.m_messageSender.Stop()
            return period

        if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.CLOSING:
            # viewer 終了待ち
            waitResult = ctypes.windll.kernel32.WaitForSingleObject(srdViewer.m_pHandle, 1)
            if WAIT_OBJECT_0 == waitResult:
                srdViewer.appendHistory("End closing Spatial Reality Display Viewer.")
                srdViewer.m_viewerStatus = srdViewer.ProcessStatus.CLOSED
                ctypes.windll.kernel32.CloseHandle(srdViewer.m_pHandle)
                srdViewer.m_pHandle = None
                srdViewer.m_pi = None
                if srdViewer.m_messageSender.IsStarted():
                    srdViewer.m_messageSender.Stop()
            return period

        waitResult = ctypes.windll.kernel32.WaitForSingleObject(srdViewer.m_pHandle, 0)
        if WAIT_TIMEOUT == waitResult:
            # タイムアウトしていたらまだプロセスは動いている
            srdViewer.m_viewerStatus = srdViewer.ProcessStatus.PROCESSING
            return period

        # 予期せずViewerが終了している場合
        if WAIT_OBJECT_0 == waitResult:
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.BOOT:
                srdViewer.appendHistory(
                    "[ERROR] Failed to connect with Spatial Reality Display Viewer.",
                    True,
                )
            elif srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                srdViewer.appendHistory("Disconnected with Spatial Reality Display Viewer.")
            srdViewer.m_viewerStatus = srdViewer.ProcessStatus.CLOSED
            ctypes.windll.kernel32.CloseHandle(srdViewer.m_pHandle)
            srdViewer.m_pHandle = None
            srdViewer.m_pi = None
            if srdViewer.m_messageSender.IsStarted():
                srdViewer.m_messageSender.Stop()

        return period

    @bpy.app.handlers.persistent
    def checkTransformCB(scene) -> None:
        if srdViewer.isLoading():
            return
        if not srdViewer.isSyncronize():
            return

        if not srdViewer.m_syncEditModel and not srdViewer.m_syncTransform:
            return

        depsgraph = bpy.context.evaluated_depsgraph_get()

        if srdViewer.m_syncEditModel:
            for update in depsgraph.updates:
                if (
                    (update.is_updated_geometry or update.is_updated_shading)
                    and isinstance(update.id, bpy.types.Object)
                    and update.id.type == "MESH"
                ):
                    # 一つの操作で複数回呼ばれる可能性があるこれに対しては
                    # updateTransformTimerCB 内で対処する
                    srdViewer.m_needReload = True
                    break

        if not srdViewer.m_syncTransform:
            return

        srdViewer.getGizmoNodes()
        if srdViewer.cameraNode is None or srdViewer.aimNode is None:
            return
        for update in depsgraph.updates:
            if update.is_updated_transform:
                if isinstance(update.id, bpy.types.Object):
                    srdViewer.checkNodeAttr(update.id)

    def updateTransformTimerCB() -> float:
        period = 0.1
        if srdViewer.isLoading():
            return period

        # fbx file の削除チェック 5秒間隔
        if srdViewer.checkFbxFileRequest():
            if srdViewer.getElapsetTimeFileDelete() > 5:
                ret = srdViewer.removeFbxFile()
                if ret:
                    srdViewer.checkFbxFileDeleteTime()
                    srdViewer.deleteFbxFileEnd()

        if not srdViewer.isSyncronize():
            return period

        if srdViewer.m_needReload:
            # ここで idle になるのを待つ
            if not CheckModal.is_operator_modal():
                # reload の判断が連続して受信される場合の再ロード抑制
                # 2秒未満の再ロード処理は行わない（正しく再ロードがかからない可能性はある）
                if srdViewer.getElapsetTimeAttrChange() < 2:
                    srdViewer.m_needReload = True
                    return period

                srdViewer.setLoading(True)

                srdViewer.load()
                srdViewer.m_changedPath.clear()
                srdViewer.m_needReload = False

                srdViewer.setLoading(False)
                srdViewer.checkAttrChangeTime()

        # Transform の更新
        camCheck = False
        for path in srdViewer.m_changedPath:
            srdViewer.SendTransformCommand(path)

            if not camCheck:
                if srdViewer.cameraNode and path == srdViewer.cameraNode.name:
                    camCheck = True

        # Camera Aim のチェックと更新
        # カメラに関係する Transform 変更に対して無条件に Gizmo の Aim を送信
        if camCheck:
            srdViewer.stateCheckSendCameraAimLength()

        srdViewer.m_changedPath.clear()

        return period

    def checkNodeAttr(path: bpy.types.Object):
        if path is None:
            return
        # aim 操作のチェック aim node 自体の Transform は送らない
        if srdViewer.aimNode.name == path.name:
            srdViewer.checkNodeAttr(srdViewer.cameraNode)
            return
        if not path.name in srdViewer.m_changedPath:  # 複数登録の防止
            # empty node の Transform は送らない
            if not path.type == "EMPTY":
                srdViewer.m_changedPath.append(path.name)
            for child in path.children:
                srdViewer.checkNodeAttr(child)

    @bpy.app.handlers.persistent
    def loadPostHandler(context):
        # タイマーコールバックを再登録
        if not bpy.app.timers.is_registered(srdViewer.updateViewerStatusTimerCB):
            srdViewer.fViewerWatchTimerCallbackId = bpy.app.timers.register(
                srdViewer.updateViewerStatusTimerCB
            )
        if not bpy.app.timers.is_registered(srdViewer.updateTransformTimerCB):
            srdViewer.fElapsedTimeCallbackId = bpy.app.timers.register(
                srdViewer.updateTransformTimerCB
            )

    @bpy.app.handlers.persistent
    def updateAnimationFrameCB(scene) -> None:
        if not srdViewer.m_syncAnimation:
            return

        srdViewer.setAnimFrame()

    def load():  # タイマーコールバック内 startViewer コール関数
        # Transform callback からコールされる
        # 処理としては load と同じだが今後の変更を想定して
        # 本メソッドからコールするとする
        if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:  # Viewer起動時のみコールする
            srdViewer.startViewer()

    # endregion

    fViewerWatchTimerCallbackId: None
    fSyncTransformCallbackId: None
    fUpdateGizmoCallbackId: None
    fElapsedTimeCallbackId: None
    fTimeChangeCallbackId: None
    fLoadPostHandlerId: None

    m_changedPath: list[str] = []
    m_viewerPath: str = ""
    m_fbxPath: str = ""  # 出力パス
    m_uniqueFileName: str = ""  # fbx ファイル名
    m_fbxPresetFile: str = ""

    # region アプリケーションで扱う固定値
    def setExecutablePath():  # 初期化時に固定
        retStringAry = os.getenv("ProgramFiles")
        srdViewer.m_viewerPath = os.path.join(
            retStringAry,
            "Sony",
            "SpatialRealityDisplayPluginBle",
            "viewer",
            "SRDViewer.exe",
        )

    def setFbxPath():  # 初期化時に固定
        retStringAry = os.getenv("LOCALAPPDATA")
        srdViewer.m_fbxPath = os.path.join(
            retStringAry, "Temp", "Sony", "SpatialRealityDisplayPluginBle"
        )

        # ディレクトリが存在しない
        if not os.path.exists(srdViewer.m_fbxPath):
            os.makedirs(srdViewer.m_fbxPath)

    def setFbxPresetPath():
        pass

    def setUniqueFbxFileName():
        randChars = "abcdefghijklmnopqrstuvwxyz"
        randFileName = ""

        for i in range(0, 8):
            sel = random.randrange(len(randChars))
            randFileName += randChars[sel]

        randFileName += ".fbx"
        srdViewer.m_uniqueFileName = randFileName

    # endregion

    # region Viewer 制御関連
    class ProcessStatus(enum.IntEnum):
        BOOT = enum.auto()
        PROCESSING = enum.auto()
        CLOSING = enum.auto()
        CLOSED = enum.auto()

    class ClippingPlane(enum.IntEnum):
        BOTH = enum.auto()
        FRONT = enum.auto()
        TOP = enum.auto()
        NONE = enum.auto()

    class ClippingMethod(enum.IntEnum):
        NONE = enum.auto()
        SAME = enum.auto()
        INC_HALF = enum.auto()

    def startViewer() -> bool:
        ret = False

        # sync 関連のフラグは落としてからロード処理を行う
        syncAnim = srdViewer.m_syncAnimation
        syncEditModel = srdViewer.m_syncEditModel
        syncTrans = srdViewer.m_syncTransform

        srdViewer.m_syncAnimation = False
        srdViewer.m_syncEditModel = False
        srdViewer.m_syncTransform = False

        try:
            ret = srdViewer.preLoadCheck()
            if not ret:
                return ret

            # Viewer 起動（起動済チェックあり)
            ret = srdViewer.stateCheckStartViewer()
            if not ret:
                return ret

            # Export 開始を送信
            ret = srdViewer.SendSetExportingCommand()
            if not ret:
                return ret

            # シーンロード・必ず再ロードかつ読み込み終了を待つ
            ret = srdViewer.stateCheckSceneLoad()
            if not ret:
                srdViewer.deleteFbxFileRequest()
                return ret

            # シーン中唯一存在する Gizmo Camera を送信
            ret = srdViewer.stateCheckSendCameraName()
            if not ret:
                srdViewer.deleteFbxFileRequest()
                return ret

            # Gizmo Camera を検索して aim distance を送信
            ret = srdViewer.stateCheckSendCameraAimLength()
            if not ret:
                return ret

            # Clipping 設定を送信
            ret = srdViewer.SendSetClippingCommand(
                srdViewer.m_clippingPlane, srdViewer.m_clippingMethod
            )

            srdViewer.deleteFbxFileRequest()
            return ret

        finally:
            # フラグを戻す(sleepが必要か？)
            srdViewer.m_syncAnimation = syncAnim
            srdViewer.m_syncEditModel = syncEditModel
            srdViewer.m_syncTransform = syncTrans
            if ret:
                ret = srdViewer.postLoadCheck()

    def bootSRDViewer() -> bool:
        # 起動もしくは再起動からのシーンロードになるので、一度通信を止める
        if srdViewer.m_messageSender.IsStarted():
            srdViewer.m_messageSender.Stop()

        if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.BOOT:
            srdViewer.appendHistory("Already starting Spatial Reality Display Viewer.")
            return False

        srdViewer.setSyncronize(False)

        if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.CLOSING:
            srdViewer.appendHistory(
                "[ERROR] Unable to start due to closing Spatial Reality Display Viewer.",
                True,
            )
            return False

        # pid をSRDViewer起動時に引数として受渡し
        pid = os.getpid()
        try:
            srdViewer.m_pi = subprocess.Popen(
                [srdViewer.m_viewerPath, "--pid", str(pid)], startupinfo=srdViewer.m_si
            )
            srdViewer.m_pHandle = ctypes.windll.kernel32.OpenProcess(
                0x001F0FFF, False, srdViewer.m_pi.pid
            )
        except Exception:
            srdViewer.m_viewerStatus = srdViewer.ProcessStatus.CLOSED
            srdViewer.appendHistory("[ERROR] CANNOT find SRDViewer.exe.", True)
            return False

        srdViewer.setSyncronize(True)

        srdViewer.m_viewerStatus = srdViewer.ProcessStatus.BOOT
        return True

    def shutdownSRDViewer() -> bool:
        if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
            srdViewer.appendHistory("Start closing Spatial Reality Display Viewer.")
            srdViewer.m_viewerStatus = srdViewer.ProcessStatus.CLOSING

            srdViewer.SendStopViewerCommand()

        elif srdViewer.m_viewerStatus == srdViewer.ProcessStatus.CLOSING:
            srdViewer.appendHistory("Already closing Spatial Reality Display Viewer.")

        elif srdViewer.m_viewerStatus == srdViewer.ProcessStatus.CLOSED:
            if srdViewer.m_messageSender.IsStarted():
                srdViewer.m_messageSender.Stop()

        return True

    m_messageSender: CommandSender = None
    m_si: subprocess.STARTUPINFO = None  # STARTUPINFOW
    m_pi: subprocess.Popen = None  # PROCESS_INFORMATION
    m_pHandle: int = None
    # endregion

    # region コマンドを発行関連 : wait を考慮した呼び出し
    def stateCheckStartViewer() -> bool:
        # debug_msg = ""

        counter = 0
        sleepTime = 500 / 1000  # sec
        retBoot = False

        if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
            # 起動済
            if not srdViewer.m_messageSender.IsStarted():
                srdViewer.m_messageSender.Start()
            return True

        serverState = Viewer.Viewer.State.Ready
        serverReplyState = Viewer.Viewer.State.Ready

        retBoot = srdViewer.bootSRDViewer()
        if not retBoot:
            return False

        def replyCB(type: IPC.Client.ReplyCBType, ret: int, msg: bytes):
            nonlocal serverReplyState
            if type == IPC.Client.ReplyCBType.Recv and ret == 0:
                reply = Viewer.ViewerCommandReply()
                if reply.Deserialize(msg):
                    serverReplyState = Viewer.Viewer.State(reply.GetExitCode())

        while True:
            time.sleep(sleepTime)
            if (
                srdViewer.m_viewerStatus != srdViewer.ProcessStatus.PROCESSING
                and srdViewer.m_pi is not None
                and srdViewer.m_pi.poll() is not None
            ):
                waitResult = ctypes.windll.kernel32.WaitForSingleObject(srdViewer.m_pHandle, 0)
                if WAIT_TIMEOUT != waitResult:
                    # MayaのloadScene 以外から viewer起動されていないかのチェック
                    # 多重起動で、自身でPopenしたprocessが終了している場合ここを通る
                    return False

            if not srdViewer.m_messageSender.IsStarted():
                srdViewer.m_messageSender.Start()
                time.sleep(sleepTime)
                continue

            viewer = Viewer.Viewer()
            getViewerStateCommand = Viewer.GetViewerStateCommand(viewer)
            srdViewer.m_messageSender.SendCommand(getViewerStateCommand, replyCB)

            if serverState != serverReplyState:
                # 起動に関してはここには来ない
                print("BOOT Process serverStatus : NOT Ready --------")
                pass

            if counter < 5:
                print("Wait 5 times for the status to change =======")
                time.sleep(sleepTime)
                counter += 1
                continue

            if serverState == serverReplyState:
                print("BOOT Process serverStatus : Ready +++++++++++++")
                break

            counter += 1
            time.sleep(sleepTime)
            if counter > 20:
                # 最大 10秒待ち　通常ここには来ない
                print("*****************TIME_OUT*********************")
                break

        srdViewer.appendHistory("Start Spatial Reality Display Viewer.")
        return True

    def stateCheckSceneLoad() -> bool:
        counter = 0
        sleepTime = 300 / 1000

        srdViewer.loadScene()

        serverState = Viewer.Viewer.State.Ready
        serverReplyState = Viewer.Viewer.State.Ready
        startWait = False
        needTimeout = False

        def replyCB(type: IPC.Client.ReplyCBType, ret: int, msg: bytes):
            nonlocal serverReplyState
            if type == IPC.Client.ReplyCBType.Recv and ret == 0:
                reply = Viewer.ViewerCommandReply()
                if reply.Deserialize(msg):
                    serverReplyState = Viewer.Viewer.State(reply.GetExitCode())

        while True:
            viewer = Viewer.Viewer()
            getViewerStateCommand = Viewer.GetViewerStateCommand(viewer)
            srdViewer.m_messageSender.SendCommand(getViewerStateCommand, replyCB)
            if serverState != serverReplyState and not startWait:
                # ここはロード中
                srdViewer.appendHistory("LOAD Process: Server Status NOT Ready")
                startWait = True
                time.sleep(sleepTime)
                counter += 1
            elif serverState != serverReplyState:
                srdViewer.appendHistory("LOAD Process: wait ...")
                time.sleep(sleepTime)
                counter += 1
                continue

            if serverState == serverReplyState and not startWait and not needTimeout:
                if counter < 5:
                    print("Wait 5 times for the status to change =======")
                else:
                    # 5回待ってもステータスチェンジが確認出来なければ強制的にフラグを上げる
                    srdViewer.appendHistory("LOAD Process: need timeout")
                    needTimeout = True
                time.sleep(sleepTime)
                counter += 1
                continue

            if serverState == serverReplyState:
                if startWait:
                    srdViewer.appendHistory("LOAD Process: Server Status Ready")
                    break
                else:
                    # ステータスチェンジを確認出来なかった
                    # シーンロードが早すぎる場合なので、5秒程度で進む事とする
                    if counter > 15:
                        srdViewer.appendHistory("LOAD Process: timeout")
                        break
                    else:
                        srdViewer.appendHistory("LOAD Process: WAIT timeout")
                        time.sleep(sleepTime)
                        counter += 1
                        continue

        return True

    def stateCheckSendCameraName() -> bool:
        name = srdViewer.getGizmoCameraName()
        if name:
            srdViewer.SendSelectCameraCommand(name)
            return True
        return False

    def stateCheckSendCameraAimLength() -> bool:
        ret = False
        aimDistance = srdViewer.getGizmoCameraAimDistance()

        ret = srdViewer.SendSetCameraAimLengthCommand(aimDistance)

        return ret

    # endregion

    # region Controller 関連
    def startAnim() -> None:
        if srdViewer.m_viewerStatus != srdViewer.ProcessStatus.PROCESSING:
            return
        srdViewer.SendAnimStartCommand()

    def stopAnim() -> None:
        if srdViewer.m_viewerStatus != srdViewer.ProcessStatus.PROCESSING:
            return
        srdViewer.SendAnimStopCommand()

    def setAnimFrame() -> None:
        if srdViewer.m_viewerStatus != srdViewer.ProcessStatus.PROCESSING:
            return
        frame, frate = srdViewer.getUnit()
        srdViewer.SendAnimationFrameCommand(frame, frate)

    def getUnit() -> typing.Tuple[int, float]:
        frate = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        frame = bpy.context.scene.frame_current
        return (frame, frate)

    def syncSettings(transform: bool, animation: bool, editModel: bool) -> None:
        currentTransFlag = srdViewer.m_syncTransform
        currentAnimFlag = srdViewer.m_syncAnimation
        currentEditFlag = srdViewer.m_syncEditModel
        if currentTransFlag != transform:
            srdViewer.m_syncTransform = transform
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                if srdViewer.m_syncTransform:
                    srdViewer.appendHistory("Sync trasnsform: ON")
                else:
                    srdViewer.appendHistory("Sync trasnsform: OFF")

        if currentAnimFlag != animation:
            srdViewer.m_syncAnimation = animation
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                if srdViewer.m_syncAnimation:
                    srdViewer.appendHistory("Sync animation frame: ON")
                else:
                    srdViewer.appendHistory("Sync animation frame: OFF")

        if currentEditFlag != editModel:
            srdViewer.m_syncEditModel = editModel
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                if srdViewer.m_syncEditModel:
                    srdViewer.appendHistory("Sync edit mesh: ON")
                else:
                    srdViewer.appendHistory("Sync edit mesh: OFF")

    def applyPanel() -> None:
        pass

    def setClippingMethod(method: int) -> None:
        currentFlag = int(srdViewer.m_clippingMethod)
        if currentFlag != method:
            if method == 1:
                srdViewer.m_clippingMethod = srdViewer.ClippingMethod.NONE
                if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                    srdViewer.appendHistory("Clipping setting: No Clip")
            elif method == 2:
                srdViewer.m_clippingMethod = srdViewer.ClippingMethod.SAME
                if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                    srdViewer.appendHistory("Clipping setting: Clip[100%]")
            elif method == 3:
                srdViewer.m_clippingMethod = srdViewer.ClippingMethod.INC_HALF
                if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                    srdViewer.appendHistory("Clipping setting: Clip[150%]")
            else:
                # ここには来ない
                srdViewer.appendHistory("[ERROR] Clipping setting: Unknown", True)

        srdViewer.SendSetClippingCommand(srdViewer.m_clippingPlane, srdViewer.m_clippingMethod)

    def setClippingPlane(front: bool, top: bool) -> None:
        if front is False and top is False:
            srdViewer.m_clippingPlane = srdViewer.ClippingPlane.NONE
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                srdViewer.appendHistory("Clipping plane: None")
        elif front is True and top is False:
            srdViewer.m_clippingPlane = srdViewer.ClippingPlane.FRONT
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                srdViewer.appendHistory("Clipping plane: Front")
        elif front is False and top is True:
            srdViewer.m_clippingPlane = srdViewer.ClippingPlane.TOP
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                srdViewer.appendHistory("Clipping plane: Top")
        elif front is True and top is True:
            srdViewer.m_clippingPlane = srdViewer.ClippingPlane.BOTH
            if srdViewer.m_viewerStatus == srdViewer.ProcessStatus.PROCESSING:
                srdViewer.appendHistory("Clipping plane: Both")

        srdViewer.SendSetClippingCommand(srdViewer.m_clippingPlane, srdViewer.m_clippingMethod)

    # endregion

    # region カメラ関連
    m_visibleGizmo = True

    def setGizmoVisibleState(visible: bool) -> None:
        srdViewer.m_visibleGizmo = visible
        srdViewer.getGizmoNodes()
        if srdViewer.gizmoNode:
            srdViewer.gizmoNode.hide_set(not srdViewer.m_visibleGizmo)

    gizmoNode: bpy.types.Object = None
    cameraNode: bpy.types.Object = None
    aimNode: bpy.types.Object = None

    def getGizmoNodes() -> None:
        try:
            srdViewer.gizmoNode.name
        except Exception:
            srdViewer.gizmoNode = None
        try:
            srdViewer.cameraNode.name
        except Exception:
            srdViewer.cameraNode = None
        try:
            srdViewer.aimNode.name
        except Exception:
            srdViewer.aimNode = None
        if srdViewer.gizmoNode is None or srdViewer.cameraNode is None or srdViewer.aimNode is None:
            # find nodes
            for o in bpy.context.scene.collection.objects:
                if o.get("gizmoForSpatialRealityDisplayNode"):
                    # find camera object
                    for oc in o.children:
                        if oc.type == "CAMERA":
                            srdViewer.cameraNode = oc
                        elif "_aim" in oc.name:
                            srdViewer.aimNode = oc
                            for aimChild in oc.children:
                                if "gizmo_node" in aimChild.name:
                                    srdViewer.gizmoNode = aimChild

    @bpy.app.handlers.persistent
    def updateGizmo(scene) -> None:
        if not srdViewer.m_visibleGizmo:
            return

        srdViewer.getGizmoNodes()
        if srdViewer.gizmoNode is None or srdViewer.cameraNode is None or srdViewer.aimNode is None:
            return

        # camera rotation to gizmo rotation
        gizmoRotate = srdViewer.cameraNode.matrix_local.to_euler()
        gizmoRotate[0] = gizmoRotate[0] - radians(45)
        srdViewer.gizmoNode.rotation_euler = gizmoRotate

        # camera location and camera lens to gizmo scale
        camLens = srdViewer.cameraNode.data.lens

        centerVal = srdViewer.getGizmoCameraAimDistance()

        # フィルム縦横（半分の値）を算出
        vFilmApertureVal = srdViewer.cameraNode.data.sensor_height / 2.0

        # tan(fovY/2)を取得
        tanFovY = vFilmApertureVal / camLens

        # カメラ位置から算出するスケール
        scaleY = tanFovY * centerVal
        scaleX = scaleY * 16.0 / 9.0  # SRD アスペクト比16:9より

        sqrt2 = 1.41421356237
        srdViewer.gizmoNode.scale = (scaleX, scaleY / sqrt2, scaleY / sqrt2)

    def createGizmoCamera() -> None:
        exGizmo = srdViewer.existsGizmoCamera()

        # Gizmo が存在しない場合のみカメラを作成
        if exGizmo == 0:
            # create camera node
            # https://docs.blender.org/api/current/bpy.types.Camera.html
            cameraData = bpy.data.cameras.new("camera1")
            cameraData.clip_start = 0.1 * 0.01
            cameraData.clip_end = 10000 * 0.01
            cameraData.lens = 35
            cameraNode = bpy.data.objects.new(cameraData.name, cameraData)

            cameraNode.location = cameraNode.location + mathutils.Vector((0, -5, 5))
            cameraNode.rotation_euler = (radians(45), 0, 0)

            # create camera group
            groupName = cameraNode.name + "_group"
            cameraGroup = bpy.data.objects.new(groupName, None)
            cameraGroup["gizmoForSpatialRealityDisplayNode"] = True  # magic property

            # create aim node
            aimName = cameraNode.name + "_aim"
            aimNode = bpy.data.objects.new(aimName, None)

            # create gizmo node
            gizmoName = "gizmo_node"
            gizmoNode = bpy.data.objects.new(gizmoName, None)
            gizmoNode.rotation_euler = (0, 0, 0)

            gizmoNode.hide_select = True
            gizmoNode["gizmoEnable"] = True
            gizmoNode.empty_display_type = "CUBE"

            # add constraints
            constraint = cameraNode.constraints.new(type="TRACK_TO")
            constraint.target = aimNode

            # set tree
            cameraNode.parent = cameraGroup
            aimNode.parent = cameraGroup
            gizmoNode.parent = aimNode

            bpy.context.scene.collection.objects.link(cameraGroup)
            bpy.context.scene.collection.objects.link(cameraNode)
            bpy.context.scene.collection.objects.link(aimNode)
            bpy.context.scene.collection.objects.link(gizmoNode)

            srdViewer.aimNode = aimNode
            srdViewer.gizmoNode = gizmoNode
            srdViewer.cameraNode = cameraNode

            if not srdViewer.m_visibleGizmo:
                gizmoNode.hide_set(True)

            # lock parameters
            gizmoNode.lock_location = (True, True, True)
            gizmoNode.lock_rotation = (True, True, True)
            gizmoNode.lock_scale = (True, True, True)

            aimNode.lock_rotation = (True, True, True)

            cameraNode.lock_rotation = (True, True, True)

            srdViewer.appendHistory("Created the camera for Spatial Reality Display Viewer.")
        else:
            srdViewer.appendHistory("[ERROR] Unable to create multiple cameras.", True)

    def existsGizmoCamera() -> None:
        cameraCount = 0
        for o in bpy.context.scene.collection.objects:
            if o.get("gizmoForSpatialRealityDisplayNode"):
                # find camera object
                for oc in o.children:
                    if oc.type == "CAMERA":
                        cameraCount += 1
                        break

        return cameraCount

    def getGizmoCameraName() -> str:
        obj = srdViewer.getGizmoCameraObject()
        if obj:
            return obj.name
        return ""

    def getGizmoCameraObject() -> bpy.types.Object:
        for o in bpy.context.scene.collection.objects:
            if o.get("gizmoForSpatialRealityDisplayNode"):
                # find camera object
                for oc in o.children:
                    if oc.type == "CAMERA":
                        return oc

        return None

    def getGizmoCameraAimDistance() -> float:
        aimDistance = 1

        srdViewer.getGizmoNodes()
        if srdViewer.aimNode is None or srdViewer.cameraNode is None:
            return aimDistance

        l1 = srdViewer.aimNode.matrix_world.to_translation()
        l2 = srdViewer.cameraNode.matrix_world.to_translation()
        aimDistance = (l1 - l2).length
        return aimDistance

    # endregion

    # region 終了処理
    def removeCallbacks() -> None:
        if srdViewer.fViewerWatchTimerCallbackId:
            bpy.app.timers.unregister(srdViewer.fViewerWatchTimerCallbackId)
        if srdViewer.fUpdateGizmoCallbackId:
            bpy.app.handlers.depsgraph_update_pre.remove(srdViewer.fUpdateGizmoCallbackId)
        if srdViewer.fSyncTransformCallbackId:
            bpy.app.handlers.depsgraph_update_post.remove(srdViewer.fSyncTransformCallbackId)
        if srdViewer.fElapsedTimeCallbackId:
            bpy.app.timers.unregister(srdViewer.fElapsedTimeCallbackId)
        if srdViewer.fTimeChangeCallbackId:
            bpy.app.handlers.frame_change_pre.remove(srdViewer.fTimeChangeCallbackId)
        if srdViewer.fLoadPostHandlerId:
            bpy.app.handlers.load_post.remove(srdViewer.fLoadPostHandlerId)

    # endregion

    # region 同期制御関連

    m_sourceOperator: bpy.types.Operator = None

    def appendHistory(log: str, errorMsg: bool = False, m=None) -> None:
        print(f"[{datetime.datetime.now()}] [{inspect.stack()[1].function}] {log}")

        if srdViewer.m_sourceOperator:
            if errorMsg:
                srdViewer.m_sourceOperator.report({"ERROR"}, log)
            else:
                srdViewer.m_sourceOperator.report({"INFO"}, log)

    def loadScene() -> None:
        srdViewer.setFbxPath()
        srdViewer.setFbxPresetPath()
        fbxFullPathName = os.path.join(srdViewer.m_fbxPath, srdViewer.m_uniqueFileName)

        try:
            # https://docs.blender.org/api/current/bpy.ops.export_scene.html
            bpy.ops.export_scene.fbx(
                filepath=fbxFullPathName,
                check_existing=False,
                filter_glob="*.fbx",
                use_selection=False,
                use_visible=False,
                use_active_collection=False,
                global_scale=1.0,
                apply_unit_scale=True,
                apply_scale_options="FBX_SCALE_ALL",
                use_space_transform=False,
                bake_space_transform=False,
                object_types={"MESH", "CAMERA", "LIGHT", "MESH", "ARMATURE", "OTHER"},
                # object_types={'MESH','LIGHT','MESH','ARMATURE','OTHER'},
                use_mesh_modifiers=True,
                use_mesh_modifiers_render=True,
                mesh_smooth_type="OFF",
                # colors_type={'NONE'},
                # prioritize_active_color=False,
                use_subsurf=False,
                use_mesh_edges=False,
                use_tspace=False,
                use_triangles=True,
                use_custom_props=False,
                add_leaf_bones=True,
                primary_bone_axis="Y",
                secondary_bone_axis="X",
                use_armature_deform_only=False,
                armature_nodetype="NULL",
                bake_anim=True,
                bake_anim_use_all_bones=False,
                bake_anim_use_nla_strips=False,
                bake_anim_use_all_actions=True,
                bake_anim_force_startend_keying=False,
                bake_anim_step=1.0,
                bake_anim_simplify_factor=0.0,
                path_mode="AUTO",
                embed_textures=False,
                batch_mode="OFF",
                use_batch_own_dir=True,
                use_metadata=True,
                axis_forward="Z",
                axis_up="Y",
            )
        except Exception:
            srdViewer.SendEndExportingCommand()

        srdViewer.appendHistory("Send the scene to Spatial Reality Display Viewer.")

        aimDistance = srdViewer.getGizmoCameraAimDistance()
        cameraName = ""
        if srdViewer.cameraNode:
            cameraName = srdViewer.cameraNode.name
        srdViewer.SendOpenCommand(fbxFullPathName, cameraName, aimDistance)

    def preLoadCheck() -> bool:
        existGizmo = srdViewer.existsGizmoCamera()
        ret = True
        if existGizmo == 0:
            srdViewer.appendHistory(
                "[ERROR] CANNOT find the camera for Spatial Reality Display Viewer.",
                True,
            )
            ret = False
        elif existGizmo > 1:
            srdViewer.appendHistory("[ERROR] Unable to place multiple cameras.", True)
            ret = False
        return ret

    def postLoadCheck() -> bool:
        if srdViewer.m_syncTransform:
            srdViewer.appendHistory("Sync trasnsform: ON")
        else:
            srdViewer.appendHistory("Sync trasnsform: OFF")
        if srdViewer.m_syncAnimation:
            srdViewer.appendHistory("Sync animation frame: ON")
        else:
            srdViewer.appendHistory("Sync animation frame: OFF")
        if srdViewer.m_syncEditModel:
            srdViewer.appendHistory("Sync edit mesh: ON")
        else:
            srdViewer.appendHistory("Sync edit mesh: OFF")

        msg = "Clipping setting: "
        if srdViewer.m_clippingMethod == srdViewer.ClippingMethod.NONE:
            msg += "No Clip"
        elif srdViewer.m_clippingMethod == srdViewer.ClippingMethod.SAME:
            msg += "Clip[100%]"
        elif srdViewer.m_clippingMethod == srdViewer.ClippingMethod.INC_HALF:
            msg += "Clip[150%]"
        srdViewer.appendHistory(msg)

        msg = "Clipping plane: "
        if srdViewer.m_clippingPlane == srdViewer.ClippingPlane.BOTH:
            msg += "Both"
        elif srdViewer.m_clippingPlane == srdViewer.ClippingPlane.FRONT:
            msg += "Front"
        elif srdViewer.m_clippingPlane == srdViewer.ClippingPlane.TOP:
            msg += "Top"
        elif srdViewer.m_clippingPlane == srdViewer.ClippingPlane.NONE:
            msg += "None"
        srdViewer.appendHistory(msg)

        return True

    def setLoading(f: bool) -> None:
        srdViewer.m_loading = f

    def isLoading() -> bool:
        return srdViewer.m_loading

    def setSyncronize(sync: bool) -> None:
        srdViewer.m_synchronize = sync

    def isSyncronize() -> bool:
        return srdViewer.m_synchronize

    def checkAttrChangeTime() -> None:
        srdViewer.m_attrChangeTimeStamp = time.time()

    def getElapsetTimeAttrChange() -> float:
        return time.time() - srdViewer.m_attrChangeTimeStamp

    def checkFbxFileDeleteTime() -> None:
        srdViewer.m_deleteFbxFileCheckTimeStamp = time.time()

    def getElapsetTimeFileDelete() -> float:
        return time.time() - srdViewer.m_deleteFbxFileCheckTimeStamp

    def deleteFbxFileRequest() -> None:
        srdViewer.m_deleteRequest = True

    def checkFbxFileRequest() -> bool:
        return srdViewer.m_deleteRequest

    def deleteFbxFileEnd():
        srdViewer.m_deleteRequest = False

    def removeFbxFile() -> bool:
        fbxFullPathName = os.path.join(srdViewer.m_fbxPath, srdViewer.m_uniqueFileName)

        if os.path.isfile(fbxFullPathName):  # ファイルが存在しない場合は削除済み
            try:
                os.remove(fbxFullPathName)
            except Exception:
                return False

        # 正常に削除後には新しいファイル名を設定
        srdViewer.setUniqueFbxFileName()
        return True

    m_synchronize: bool = False  # IPC 通信フラグ
    m_syncTransform: bool = False
    m_syncAnimation: bool = False
    m_syncEditModel: bool = False
    m_needReload: bool = False
    m_loading: bool = False
    m_attrChangeTimeStamp: float = 0.0
    m_deleteFbxFileCheckTimeStamp: float = 0.0
    m_deleteRequest: bool = False
    m_viewerStatus: ProcessStatus = ProcessStatus.BOOT
    m_clippingPlane: ClippingPlane = ClippingPlane.NONE
    m_clippingMethod: ClippingMethod = ClippingMethod.NONE
    # endregion

    # region コマンド関連
    def SendOpenCommand(open_path: str, camera_name: str, aim_length: float) -> bool:
        ret = False
        view = Viewer.Viewer()
        openSceneCmd = Viewer.OpenSceneCommand(view)
        openSceneCmd.SetOpenPath(open_path)
        openSceneCmd.AddOption("camera", camera_name)
        openSceneCmd.AddOption("aim_length", aim_length)

        ret = srdViewer.m_messageSender.SendCommand(openSceneCmd)
        if ret:
            srdViewer.appendHistory("Succeeded in sending the scene")
        else:
            srdViewer.appendHistory("[ERROR] Failure in sending the scene.")

        return ret

    def SendTransformCommand(path: str) -> bool:
        ret = False

        obj = bpy.context.scene.objects.get(path)

        if obj is None:
            return True

        view = Viewer.Viewer()
        transCmd = Viewer.SetObjectTransformCommand(view)

        transCmd.SetTransform(obj.matrix_world)
        transCmd.SetTransformName(path)

        ret = srdViewer.m_messageSender.SendCommand(transCmd)

        if ret:
            srdViewer.appendHistory(f"Load Transform Success {path}")
        else:
            srdViewer.appendHistory(f"Load Transform Failure {path}")

        return ret

    def SendAnimStartCommand() -> bool:
        ret = False
        view = Viewer.Viewer()
        animStartCmd = Viewer.StartAnimationCommand(view)

        ret = srdViewer.m_messageSender.SendCommand(animStartCmd)
        srdViewer.appendHistory("Succeeded in starting animation.")

        return ret

    def SendAnimStopCommand() -> bool:
        ret = False
        view = Viewer.Viewer()
        stopAnimCmd = Viewer.StopAnimationCommand(view)

        ret = srdViewer.m_messageSender.SendCommand(stopAnimCmd)
        srdViewer.appendHistory("Succeeded in stopping animation.")

        return ret

    def SendAnimationFrameCommand(frame: int, frate: float) -> bool:
        ret = False
        view = Viewer.Viewer()
        animFrameCmd = Viewer.SetAnimationFrameCommand(view)
        animFrameCmd.SetFPS(frate)
        animFrameCmd.SetFrame(frame)

        ret = srdViewer.m_messageSender.SendCommand(animFrameCmd)
        srdViewer.appendHistory(f"Succeeded in setting animation frame {frame} / {frate} [fps].")

        return ret

    def SendSelectCameraCommand(camName) -> bool:
        ret = False
        view = Viewer.Viewer()
        selectCameraCmd = Viewer.SelectCamera(view)

        selectCameraCmd.SetSelectedCameraName(camName)
        ret = srdViewer.m_messageSender.SendCommand(selectCameraCmd)

        msg = "select camera "
        msg += camName
        msg += " "
        if ret:
            msg += "Success"
        else:
            msg += "Failure"

        srdViewer.appendHistory(msg)

        return True

    def SendSetCameraAimLengthCommand(aimLength: float) -> bool:
        ret = False
        view = Viewer.Viewer()
        aimCmd = Viewer.SetCameraAimLengthCommand(view)

        aimCmd.SetCameraAimLength(aimLength)

        ret = srdViewer.m_messageSender.SendCommand(aimCmd)

        msg = "set camera aim length: "
        msg += str(aimLength)
        msg += " "
        if ret:
            msg += "Success"
        else:
            msg += "Failure"

        srdViewer.appendHistory(msg)

        return ret

    def SendStopViewerCommand() -> bool:
        ret = False
        view = Viewer.Viewer()
        stopViewCmd = Viewer.StopViewerCommand(view)

        ret = srdViewer.m_messageSender.SendCommand(stopViewCmd)

        msg = "viewer stop "
        if ret:
            msg += "Success"
        else:
            msg += "Failure"

        srdViewer.appendHistory(msg)

        return ret

    def SendSetExportingCommand() -> bool:
        view = Viewer.Viewer()
        startExpCmd = Viewer.StartExportingCommand(view)
        ret = srdViewer.m_messageSender.SendCommand(startExpCmd)
        msg = "FBX Exporting "
        if ret:
            msg += "Success"
        else:
            msg += "Failure"

        srdViewer.appendHistory(msg)

        return ret

    def SendEndExportingCommand() -> bool:
        ret = False

        view = Viewer.Viewer()
        endExpCmd = Viewer.EndExportingCommand(view)
        ret = srdViewer.m_messageSender.SendCommand(endExpCmd)
        msg = "FBX Cancel Exporting "
        if ret:
            msg += "Success"
        else:
            msg += "Failure"

        srdViewer.appendHistory(msg)

        return ret

    def SendSetClippingCommand(plane: ClippingPlane, method: ClippingMethod) -> bool:
        ret = False
        view = Viewer.Viewer()
        clipCmd = Viewer.SetClippingCommand(view)
        clipCmd.SetPlane(int(plane))
        clipCmd.SetMethod(int(method))

        ret = srdViewer.m_messageSender.SendCommand(clipCmd)

        return ret

    # endregion
