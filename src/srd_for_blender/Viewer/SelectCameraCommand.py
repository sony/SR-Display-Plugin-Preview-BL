import fbs.Viewer.fbs.SelectCameraCommand as FbsSelectCameraCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class SelectCamera(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_selectCameraName = ""

    def __del__(self):
        pass

    def SetSelectedCameraName(self, camName: str) -> None:
        self.m_selectCameraName = camName

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.SelectCamera

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        if not self.m_selectCameraName:
            return False

        objName = self.m_selectCameraName
        name = builder.CreateString(objName, encoding="utf-8")
        FbsSelectCameraCommand.Start(builder)
        FbsSelectCameraCommand.AddName(builder, name)
        cmd = FbsSelectCameraCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        cmd = FbsSelectCameraCommand.SelectCameraCommand.GetRootAs(data)
        self.m_openPath = cmd.Name()
        return True
