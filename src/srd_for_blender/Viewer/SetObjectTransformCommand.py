import fbs.Viewer.fbs.SetObjectTransformCommand as FbsSetObjectTransformCommand
import fbs.Viewer.fbs.Transform as Transform
import flatbuffers
from mathutils import Matrix

from .ViewerCommand import Viewer, ViewerCommand


class SetObjectTransformCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_transform = Matrix()
        self.m_transformName = ""

    def __del__(self):
        pass

    def SetTransform(self, m: Matrix) -> None:
        self.m_transform = m

    def SetTransformName(self, trnName: str) -> None:
        self.m_transformName = trnName

    def Exec(self) -> bool:
        return True

    @staticmethod
    def GetStaticId() -> ViewerCommand.Id:
        return ViewerCommand.Id.SetObjectTransform

    def GetId(self) -> ViewerCommand.Id:
        return SetObjectTransformCommand.GetStaticId()

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        name = builder.CreateString(self.m_transformName, encoding="utf-8")

        FbsSetObjectTransformCommand.Start(builder)

        FbsSetObjectTransformCommand.AddName(builder, name)

        # mathutil.Matrixをflat化してTransformを作成
        m = self.m_transform

        # MayaのTRS行列に変換
        mx = [
            m.row[0][0],
            m.row[1][0],
            m.row[2][0],
            m.row[3][0],
            m.row[0][1],
            m.row[1][1],
            m.row[2][1],
            m.row[3][1],
            m.row[0][2],
            m.row[1][2],
            m.row[2][2],
            m.row[3][2],
            m.row[0][3],
            m.row[1][3],
            m.row[2][3],
            m.row[3][3],
        ]
        # itertools.chain.from_iterableのほうが高速
        # FbsSetObjectTransformCommand.AddTransform(builder,Transform.CreateTransform(builder,list(itertools.chain.from_iterable(m.row))))
        # FbsSetObjectTransformCommand.AddTransform(
        #     builder, Transform.CreateTransform(builder, [x for row in m.row for x in row])
        # )
        FbsSetObjectTransformCommand.AddTransform(builder, Transform.CreateTransform(builder, mx))
        cmd = FbsSetObjectTransformCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        cmd = FbsSetObjectTransformCommand.SetObjectTransformCommand.GetRootAs(data)
        # objName = cmd.Name()
        m = cmd.Transform().Matrix()
        self.m_transform = Matrix((tuple(m[0:4]), tuple(m[4:8]), tuple(m[8:12]), tuple(m[12:16])))
        return True
