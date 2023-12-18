from typing import Callable

import fbs.IPCViewerCommand.fbs.IPCMessage as FbsIPCMessage
import fbs.IPCViewerCommand.fbs.MessageData as FbsMessageData
import fbs.IPCViewerCommand.fbs.ViewerCommand as FbsViewerCommand
import flatbuffers
import IPC
import Viewer


class CommandSender:
    def __init__(self, url: str):
        self.m_url = url

        logCB = IPC.LogCallback()
        # logCB.m_error = print
        # logCB.m_warn = print
        # logCB.m_info = print
        # logCB.m_debug = print
        # logCB.m_trace = print

        self.m_client = IPC.Client()
        self.m_client.SetLogCallback(logCB)
        self.m_client.SetSendTimeout(300)
        self.m_client.SetReceiveTimeout(300)

    def __del__(self):
        pass

    def Start(self):
        self.m_client.Start(self.m_url)

    def Stop(self):
        self.m_client.Stop()

    def IsStarted(self) -> bool:
        return self.m_client.IsStarted()

    def SendCommand(
        self,
        cmd: Viewer.ViewerCommand,
        replyCB: Callable[[IPC.Client.ReplyCBType, int, bytes], None] = None,
    ):
        cmdBuilder = flatbuffers.Builder()
        cmd.Serialize(cmdBuilder)

        messageBuilder = flatbuffers.Builder()
        body = messageBuilder.CreateByteVector(cmdBuilder.Output())
        FbsViewerCommand.Start(messageBuilder)
        FbsViewerCommand.AddId(messageBuilder, cmd.GetId())
        FbsViewerCommand.AddBody(messageBuilder, body)
        viewerCmd = FbsViewerCommand.End(messageBuilder)
        FbsIPCMessage.Start(messageBuilder)
        FbsIPCMessage.AddDataType(messageBuilder, FbsMessageData.MessageData.ViewerCommand)
        FbsIPCMessage.AddData(messageBuilder, viewerCmd)
        message = FbsIPCMessage.End(messageBuilder)
        messageBuilder.Finish(message)

        msg = messageBuilder.Output()

        self.m_client.Send(bytes(msg), replyCB)

        return True
