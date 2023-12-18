import ctypes
import enum
import threading
from collections import deque
from threading import Thread
from typing import Callable, Deque

import pynng

from .LogCallback import LogCallback


class Client:
    def __init__(self):
        self.m_started = False
        self.m_socket: pynng.Socket = None
        self.m_dialer: pynng.Dialer = None
        self.m_works: list[Client.Work] = []
        self.m_freeWorks: Deque[Client.Work] = deque([])
        self.m_freeWorksMutex = threading.Lock()
        self.m_log = LogCallback()
        self.m_sendTimeout = -1
        self.m_receiveTimeout = -1
        self.m_errorCount = 0

    def __del__(self):
        self.Stop()

    def SetLogCallback(self, logCB: LogCallback):
        self.m_log = logCB

    def SetSendTimeout(self, timeout: int):
        self.m_sendTimeout = timeout

    def SetReceiveTimeout(self, timeout: int):
        self.m_receiveTimeout = timeout

    def Start(self, url: str) -> bool:
        self.Stop()
        self.m_log.Info("Start IPCClient")
        self.m_errorCount = 0

        try:
            self.m_socket = pynng.Req0(
                recv_timeout=self.m_receiveTimeout, send_timeout=self.m_sendTimeout
            )
        except Exception:
            self.m_log.Error("Failed nng_req0_open()")
            return False

        try:
            self.m_dialer = self.m_socket.dial(url, block=True)
        except Exception:
            self.m_log.Error("Failed nng_dialer_create()")
            self.m_socket.close()
            return False

        self.m_started = True
        self.m_log.Info("Successful IPCClient start")
        return True

    def Stop(self):
        if self.m_started:
            # nng_ctx_closeを明示的に実行
            for work in self.m_works:
                work.Close()
            for work in self.m_freeWorks:
                work.Close()
            self.m_works.clear()

            self.m_freeWorks.clear()

            try:
                self.m_dialer.close()
                self.m_socket.close()
            except Exception:
                pass
            self.m_started = False
            self.m_log.Info("Stop IPC Client")

    def IsStarted(self) -> bool:
        return self.m_started

    def GetErrorCount(self) -> int:
        return self.m_errorCount

    class ReplyCBType(enum.IntEnum):
        Send = enum.auto()
        Recv = enum.auto()

    def Send(self, message: bytes, replyCB: Callable[[ReplyCBType, int, bytes], None]):
        self.m_log.Trace("Client::Send()")

        if not self.m_started:
            return False

        try:
            self.m_freeWorksMutex.acquire()

            work = None

            if len(self.m_freeWorks) != 0:
                work = self.m_freeWorks.popleft()
            else:
                try:
                    ctx = self.m_socket.new_context()
                except Exception:
                    self.m_log.Error("Failed nng_ctx_open()")
                    return False
                p = Client.Work()
                p.m_ctx = ctx

                p.m_aio = Client.AIO(Client.WorkCB, p)

                p.m_client = self

                work = p
                self.m_works.append(work)

            work.m_msg = message

            work.m_aio.message = work.m_msg
            work.m_msg = None

            work.m_replyCB = replyCB

            work.m_state = Client.State.Send

            work.m_aio.Send(work.m_ctx)
        finally:
            if self.m_freeWorksMutex.locked():
                self.m_freeWorksMutex.release()

        return True

    # pynngはaioのコールバックが未実装なので独自に定義
    class AIO:
        class WorkThread(Thread):
            def __init__(self, task, callback):
                super().__init__(daemon=True)
                self.task = task
                self.callback = callback

            def run(self):
                result = self.task()
                self.callback(result)

            def kill(self):
                if self.is_alive():
                    ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                        self.native_id, ctypes.py_object(SystemExit)
                    )
                    if ret > 1:
                        ctypes.pythonapi.PyThreadState_SetAsyncExc(self.native_id, None)

        def __init__(self, workCB, work):
            self.workCB = workCB
            self.work = work
            self.message = None
            self.thread = None
            self.result = -1

        def SendTask(self, ctx: pynng.Context):
            try:
                ctx.send(self.message)
                return 0
            except Exception:
                return -1

        def RecvTask(self, ctx: pynng.Context):
            try:
                self.message = ctx.recv()
                return 0
            except Exception:
                return -1

        def SendCallback(self, result):
            self.result = result
            if self.workCB:
                self.workCB(self.work)

        def RecvCallback(self, result):
            self.result = result
            if self.workCB:
                self.workCB(self.work)

        def Send(self, context: pynng.Context):
            self.thread = Client.AIO.WorkThread(lambda: self.SendTask(context), self.SendCallback)
            self.thread.start()

        def Recv(self, context: pynng.Context):
            self.thread = Client.AIO.WorkThread(lambda: self.RecvTask(context), self.RecvCallback)
            self.thread.start()

        def Close(self):
            if self.thread:
                self.workCB = None

    class State(enum.IntEnum):
        Init = enum.auto()
        Send = enum.auto()
        Recv = enum.auto()

    class Work:
        def __init__(self):
            self.m_state = Client.State.Init
            self.m_ctx: pynng.Context = None
            self.m_aio: Client.AIO = None
            self.m_msg: str = None
            self.m_replyCB: Callable[[Client.ReplyCBType, int, bytes], None] = None
            self.m_client: Client = None

        def Close(self):
            # 自身のwork threadを強制終了させる
            if self.m_aio:
                self.m_aio.Close()
            try:
                if self.m_ctx:
                    self.m_ctx.close()
            except Exception:
                pass

    @staticmethod
    def WorkCB(work: Work) -> None:
        if work is None:
            return
        work.m_client.StepWork(work)

    def StepWork(self, work: Work) -> None:
        try:
            ret = 0
            if work.m_state == Client.State.Init:
                pass
            elif work.m_state == Client.State.Send:
                self.m_log.Trace("IPCClient State::Send")
                ret = work.m_aio.result
                if ret == 0:
                    work.m_state = Client.State.Recv
                    work.m_aio.Recv(work.m_ctx)

                else:
                    self.m_errorCount += 1
                    self.m_log.Error(f"IPCClient Failed State::Send[{ret}]")

                    if work.m_replyCB:
                        # 送信失敗時は空のリプライを返す
                        work.m_replyCB(Client.ReplyCBType.Send, ret, "".encode("utf-8"))
                    work.m_replyCB = None
                    # 送信に失敗したら m_freeWorks に追加しておく
                    self.m_freeWorksMutex.acquire()
                    work.m_state = Client.State.Init
                    self.m_freeWorks.append(work)
            elif work.m_state == Client.State.Recv:
                self.m_log.Trace("IPCClient State::Recv")
                ret = work.m_aio.result
                if ret == 0:
                    # エラーカウントをリセットする
                    self.m_errorCount = 0

                    work.m_msg = work.m_aio.message
                    if work.m_replyCB:
                        work.m_replyCB(Client.ReplyCBType.Recv, ret, work.m_msg)
                else:
                    # エラーカウントを上げる
                    self.m_errorCount += 1
                    self.m_log.Error(f"IPCClient Failed State::Recv[{ret}]")
                    if work.m_replyCB:
                        work.m_replyCB(Client.ReplyCBType.Recv, ret, "".encode("utf-8"))
                    work.m_replyCB = None
                    # m_freeWorks に追加しておく
                    self.m_freeWorksMutex.acquire()
                    work.m_state = Client.State.Init
                    self.m_freeWorks.append(work)
        finally:
            if self.m_freeWorksMutex.locked():
                self.m_freeWorksMutex.release()
