import fbs.Viewer.fbs.SetClippingCommand as FbsSetClippingCommand
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class SetClippingCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_method = 0
        self.m_plane = 0

    def __del__(self):
        pass

    def Exec(self) -> bool:
        viewer = self.GetViewer()
        if not viewer:
            print("SetClippingCommand::Exec(): Viewer is None.")
            return False

        method = Viewer.ClippingMethod(self.m_method)
        plane = Viewer.ClippingPlane(self.m_plane)
        viewer.SetClippingMethod(method)
        viewer.SetClippingPlane(plane)

        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.SetClipping

    def SetMethod(self, method: int) -> None:
        self.m_method = method

    def GetMethod(self) -> int:
        return self.m_method

    def SetPlane(self, plane: int) -> None:
        self.m_plane = plane

    def GetPlane(self) -> int:
        return self.m_plane

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        FbsSetClippingCommand.Start(builder)
        FbsSetClippingCommand.AddMethod(builder, self.m_method)
        FbsSetClippingCommand.AddPlane(builder, self.m_plane)
        cmd = FbsSetClippingCommand.End(builder)
        builder.Finish(cmd)

        return True

    def Deserialize(self, data, dataSize) -> bool:
        cmd = FbsSetClippingCommand.SetClippingCommand.GetRootAs(data)
        self.m_method = cmd.Method()
        self.m_plane = cmd.Plane()

        return True
