"""测试夹具 — 独立 SQLite 文件库 + 可编排的假模型。

@why 环境变量必须在 import app 之前设置：app.config / app.db 在导入时读取配置。
     假模型只替换 llm.complete_with_tools 这一个网络边界，引擎、工具、落库全走真实代码。
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="ocft-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
# @why config.yaml 优先级最高：测试指向不存在的配置文件，防止连到真实云库 / Redis
os.environ["OCFT_DB_CONFIG"] = (_TMP / "absent-config.yaml").as_posix()
os.environ["LLM_API_KEY"] = "test-key-not-real"
os.environ["LLM_MODEL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import llm  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # 触发 lifespan：模型锁定校验 + 建表 + 幂等种子
        yield c


def tool_call(call_id: str, name: str, arguments: str) -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments}}


def model_reply(content: str | None = None, tool_calls: list | None = None,
                tokens: int = 10) -> dict:
    return {"content": content, "tool_calls": tool_calls or [],
            "usage": {"prompt_tokens": tokens, "completion_tokens": 0, "total_tokens": tokens},
            "model": "deepseek-v4.1-flash", "finish_reason": "stop"}


@pytest.fixture
def fake_llm(monkeypatch):
    """按顺序返回预设的模型响应；记录每次收到的 messages 与 timeout 供断言。
    响应可以是 dict、异常，或无参可调用对象（用于模拟慢模型，返回 dict）。"""
    state = {"replies": [], "calls": []}

    def _fake(messages, tools, temperature=0.2, timeout=None, max_tokens=None, thinking=None):
        state["calls"].append({"messages": list(messages), "tools": tools, "timeout": timeout,
                               "max_tokens": max_tokens})
        if not state["replies"]:
            raise AssertionError("假模型响应已用完")
        reply = state["replies"].pop(0)
        if callable(reply):
            reply = reply()
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm, "complete_with_tools", _fake)
    return state


HEADERS = {"X-Actor-Id": "tester"}
