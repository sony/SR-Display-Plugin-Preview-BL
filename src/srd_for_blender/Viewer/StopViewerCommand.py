import fbs.Viewer.fbs.StopViewerCommand as FbsStopViewerCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class StopViewerCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)

    def __del__(self):
        pass

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.StopViewer

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsStopViewerCommand.Start(builder)
        cmd = FbsStopViewerCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data, dataSize) -> bool:
        FbsStopViewerCommand.StopViewerCommand.GetRootAs(data)
        return True
