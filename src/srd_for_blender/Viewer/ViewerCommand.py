import enum
from abc import ABCMeta, abstractmethod

import fbs.Viewer.fbs.Reply as fbs
import flatbuffers


class Viewer:
    class State(enum.IntEnum):
        Ready = 0
        Loading = enum.auto()

    class DisplayState(enum.IntEnum):
        Ready = 0
        SceneLoading = enum.auto()
        SceneViewing = enum.auto()
        FbxExporting = enum.auto()

    class ClippingPlane(enum.IntEnum):
        BOTH = 1
        FRONT = enum.auto()
        TOP = enum.auto()
        NONE = enum.auto()

    class ClippingMethod(enum.IntEnum):
        NONE = 1
        SAME = enum.auto()
        INC_HALF = enum.auto()

    def __init__(self):
        self.m_state = Viewer.State.Ready
        self.m_displayState = Viewer.DisplayState.Ready
        self.m_requestExit = False
        self.m_clpPlane = Viewer.ClippingPlane.BOTH
        self.m_clpMethod = Viewer.ClippingMethod.NONE

    def SetExitRequest(self) -> None:
        self.m_requestExit = False

    def IsRequestExit(self) -> bool:
        return self.m_requestExit

    def GetState(self) -> State:
        return self.m_state

    def GetDisplayState(self) -> DisplayState:
        return self.m_displayState

    def SetState(self, state: State) -> None:
        self.m_state = state

    def SetDisplayState(self, state: DisplayState) -> None:
        self.m_displayState = state

    def GetClippiongPlane(self) -> ClippingPlane:
        return self.m_clpPlane

    def SetClippingPlane(self, plane: ClippingPlane) -> None:
        self.m_clpPlane = plane

    def GetClippingMethod(self) -> ClippingMethod:
        return self.m_clpMethod

    def SetClippingMethod(self, method: ClippingMethod) -> None:
        self.m_clpMethod = method


class ViewerCommand:
    __metaclass__ = ABCMeta

    class Id(enum.IntEnum):
        OpenScene = enum.auto()
        SetObjectTransform = enum.auto()
        StartAnimation = enum.auto()
        StopAnimation = enum.auto()
        SetAnimationFrame = enum.auto()
        GetViewerState = enum.auto()
        SelectCamera = enum.auto()
        SetCameraAimLength = enum.auto()
        EditCameraAim = enum.auto()
        StopViewer = enum.auto()
        StartExporting = enum.auto()
        EndExporting = enum.auto()
        SetClipping = enum.auto()

    def __init__(self, viewer: Viewer):
        self.m_viewer = viewer
        self.m_exitCode = 0
        self.m_exitMessage = ""

    @abstractmethod
    def __del__(self):
        pass

    @abstractmethod
    def Exec(self) -> bool:
        pass

    @abstractmethod
    def GetId(self) -> Id:
        pass

    @abstractmethod
    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        pass

    @abstractmethod
    def Deserialize(self, data) -> bool:
        pass

    def GetExitCode(self) -> int:
        return self.m_exitCode

    def GetExitMessage(self) -> str:
        return self.m_exitMessage

    def GetViewer(self) -> Viewer:
        return self.m_viewer

    def SetExitCode(self, code: int) -> None:
        self.m_exitCode = code

    def SetExitMessage(self, message: str) -> None:
        self.m_exitMessage = message


class ViewerCommandReply:
    def __init__(self):
        self.m_exitCode = 0
        self.m_exitMessage = ""

    def SetExitCode(self, code: int) -> None:
        self.m_exitCode = code

    def GetExitCode(self) -> int:
        return self.m_exitCode

    def SetExitMessage(self, message: str) -> None:
        self.m_exitMessage = message

    def GetExitMessage(self) -> str:
        return self.m_exitMessage

    def Deserialize(self, data) -> bool:
        cmd = fbs.Reply.GetRootAs(data)
        self.m_exitCode = cmd.Code()
        self.m_exitMessage = cmd.Message()
        return True
