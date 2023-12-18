import fbs.Viewer.fbs.SetAnimationFrameCommand as FbsSetAnimationFrameCommand
import fbs.Viewer.fbs.StartAnimationCommand as FbsStartAnimationCommand
import fbs.Viewer.fbs.StopAnimationCommand as FbsStopAnimationCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class StartAnimationCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)

    def __del__(self):
        pass

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.StartAnimation

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsStartAnimationCommand.Start(builder)
        cmd = FbsStartAnimationCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        FbsStartAnimationCommand.StartAnimationCommand.GetRootAs(data)
        return True


class StopAnimationCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)

    def __del__(self):
        pass

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.StopAnimation

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsStopAnimationCommand.Start(builder)
        cmd = FbsStopAnimationCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        FbsStopAnimationCommand.StopAnimationCommand.GetRootAs(data)
        return True


class SetAnimationFrameCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_frame = 0
        self.m_fps = 60.0

    def __del__(self):
        pass

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.SetAnimationFrame

    def SetFrame(self, frame: int) -> None:
        self.m_frame = frame

    def GetFrame(self) -> int:
        return self.m_frame

    def SetFPS(self, fps: float) -> None:
        self.m_fps = fps

    def GetFPS(self) -> float:
        return self.m_fps

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsSetAnimationFrameCommand.Start(builder)
        FbsSetAnimationFrameCommand.AddFps(builder, self.m_fps)
        FbsSetAnimationFrameCommand.AddFrame(builder, self.m_frame)
        cmd = FbsSetAnimationFrameCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        cmd = FbsSetAnimationFrameCommand.SetAnimationFrameCommand.GetRootAs(data)
        self.m_fps = cmd.Fps()
        self.m_frame = cmd.Frame()
        return True
