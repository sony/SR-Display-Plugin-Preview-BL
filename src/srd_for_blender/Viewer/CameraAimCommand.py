import fbs.Viewer.fbs.EditCameraAimCommand as FbsEditCameraAimCommand
import fbs.Viewer.fbs.SetCameraAimLengthCommand as FbsSetCameraAimLengthCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class SetCameraAimLengthCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_cameraAimLength = 100.0

    def __del__(self):
        pass

    def SetCameraAimLength(self, length: float) -> None:
        self.m_cameraAimLength = length

    def GetCameraAimLength(self) -> float:
        return self.m_cameraAimLength

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.SetCameraAimLength

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsSetCameraAimLengthCommand.Start(builder)
        FbsSetCameraAimLengthCommand.AddAimLength(builder, self.m_cameraAimLength)
        cmd = FbsSetCameraAimLengthCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        cmd = FbsSetCameraAimLengthCommand.SetCameraAimLengthCommand.GetRootAs(data)
        self.m_cameraAimLength = cmd.AimLength()
        return True


class EditCameraAimCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_edit = False

    def __del__(self):
        pass

    def EnableEdit(self, enable: bool) -> None:
        self.m_edit = enable

    def Enabled(self) -> bool:
        return self.m_edit

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.SetCameraAimLength

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsEditCameraAimCommand.Start(builder)
        FbsEditCameraAimCommand.AddEdit(builder, self.m_edit)
        cmd = FbsEditCameraAimCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        cmd = FbsEditCameraAimCommand.EditCameraAimCommand.GetRootAs(data)
        self.m_edit = cmd.Edit()
        return True
