"""类型化异常 — code + is_retryable 供工具循环与 API 统一消费。"""


class LLMError(Exception):
    """模型调用失败：code ∈ not_configured | auth_failed | rate_limited | bad_request | timeout | unavailable | bad_json。"""

    def __init__(self, code: str, message: str, is_retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.is_retryable = is_retryable


class ToolError(Exception):
    """工具执行失败：code ∈ invalid_args | not_found | execution_failed | not_allowed。"""

    def __init__(self, code: str, message: str, is_retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.is_retryable = is_retryable


class RunTimeoutError(Exception):
    """单次 run 超出时限（设计 §8：60 秒起点）。"""

    def __init__(self, message: str = "run 执行超出时限"):
        super().__init__(message)
        self.code = "run_timeout"
