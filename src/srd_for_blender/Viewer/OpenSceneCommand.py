import fbs.Viewer.fbs.OpenSceneCommand as FbsOpenSceneCommand
import fbs.Viewer.fbs.Option as Option
import flatbuffers

from .ViewerCommand import Viewer, ViewerCommand


class OpenSceneCommand(ViewerCommand):
    def __init__(self, viewer: Viewer):
        super().__init__(viewer)
        self.m_openPath = ""
        self.m_options: dict[str, str] = {}

    def __del__(self):
        pass

    def SetOpenPath(self, path: str) -> None:
        self.m_openPath = path

    def GetOpenPath(self) -> str:
        return self.m_openPath

    def AddOption(self, key: str, value) -> None:
        self.m_options[key] = str(value)

    def GetOption(self, key, str) -> str:
        result = self.m_options.get(key)
        if not result:
            return ""
        return result

    def Exec(self) -> bool:
        return True

    def GetId(self) -> ViewerCommand.Id:
        return ViewerCommand.Id.OpenScene

    def Serialize(self, builder: flatbuffers.Builder) -> bool:
        optionVec = []
        for key, value in self.m_options.items():
            key = builder.CreateString(key, encoding="utf-8")
            value = builder.CreateString(value, encoding="utf-8")
            Option.Start(builder)
            Option.AddKey(builder, key)
            Option.AddValue(builder, value)
            option = Option.End(builder)
            optionVec += [option]

        FbsOpenSceneCommand.StartOptionsVector(builder, len(optionVec))
        for option in optionVec:
            builder.PrependUOffsetTRelative(option)
        options = builder.EndVector(len(optionVec))

        path = builder.CreateString(self.m_openPath, encoding="utf-8")
        FbsOpenSceneCommand.Start(builder)
        FbsOpenSceneCommand.AddPath(builder, path)
        FbsOpenSceneCommand.AddOptions(builder, options)
        cmd = FbsOpenSceneCommand.End(builder)
        builder.Finish(cmd)
        return True

    def Deserialize(self, data) -> bool:
        cmd = FbsOpenSceneCommand.OpenSceneCommand.GetRootAs(data)
        self.m_openPath = cmd.Path()
        self.m_options.clear()
        for i in range(cmd.OptionsLength()):
            optionIt = cmd.Options(i)
            self.m_options[optionIt.Key()] = optionIt.Value()
        return True
