import fbs.Viewer.fbs.GetViewerStateCommand as FbsGetViewerStateCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class GetViewerStateCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)

    def __del__(self):
        pass

    def Exec(self) -> bool:
        viewer = self.GetViewer()
        state = viewer.GetState()
        self.SetExitCode(int(state))
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.GetViewerState

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsGetViewerStateCommand.Start(builder)
        cmd = FbsGetViewerStateCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data, dataSize) -> bool:
        FbsGetViewerStateCommand.GetViewerStateCommand.GetRootAs(data)
        return True
