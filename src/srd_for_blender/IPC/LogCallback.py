class LogCallback:
    def __init__(self):
        self.m_error = None
        self.m_warn = None
        self.m_info = None
        self.m_debug = None
        self.m_trace = None

    def Error(self, massage: str) -> None:
        if self.m_error:
            self.m_error(massage)

    def Warn(self, massage: str) -> None:
        if self.m_warn:
            self.m_warn(massage)

    def Info(self, massage: str) -> None:
        if self.m_info:
            self.m_info(massage)

    def Debug(self, massage: str) -> None:
        if self.m_debug:
            self.m_debug(massage)

    def Trace(self, massage: str) -> None:
        if self.m_trace:
            self.m_trace(massage)
