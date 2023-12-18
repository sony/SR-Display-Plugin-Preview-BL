import fbs.Viewer.fbs.EndExportingCommand as FbsEndExportingCommand
import fbs.Viewer.fbs.StartExportingCommand as FbsStartExportingCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class StartExportingCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)

    def __del__(self):
        pass

    def Exec(self) -> bool:
        viewer = self.GetViewer()
        if viewer is None:
            print("StartExportingCommand::Exec(): Viewer is None.")
            return False

        viewer.SetDisplayState(Viewer.DisplayState.FbxExporting)

        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.StartExporting

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsStartExportingCommand.Start(builder)
        cmd = FbsStartExportingCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        FbsStartExportingCommand.StartExportingCommand.GetRootAs(data)
        return True


class EndExportingCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)

    def __del__(self):
        pass

    def Exec(self) -> bool:
        viewer = self.GetViewer()
        if viewer is None:
            print("EndExportCommand::Exec(): Viewer is None.")
            return False

        viewer.SetDisplayState(Viewer.DisplayState.Ready)

        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.EndExporting

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsEndExportingCommand.Start(builder)
        cmd = FbsEndExportingCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        FbsEndExportingCommand.EndExportingCommand.GetRootAs(data)
        return True
