"""LLM 唯一调用入口 — 类型化错误、超时、usage 记录、原生工具调用。

@why 禁静默降级：所有失败以 LLMError 抛出（带 code/is_retryable），
     由调用方决定返回结构化错误还是降级展示规则事实（必须显式标注来源）。
     usage 每次调用返回，供 run 记录 token 消耗与费用估算。
"""
import json
import time
from datetime import datetime, timezone

from .config import settings
from .domain.errors import LLMError

# 近期模型连通状态：被动记录真实调用结果，不做主动探测（省 token、不伪造"已检查"）
_recent = {"status": "unknown", "error_code": None, "checked_at": None}


def recent_status() -> dict:
    """health/ready 消费：ok / error / unknown / not_configured。"""
    if not settings.llm_enabled:
        return {"status": "not_configured", "error_code": "not_configured",
                "checked_at": None}
    return dict(_recent)


def _note(status: str, error_code: str | None = None) -> None:
    _recent["status"] = status
    _recent["error_code"] = error_code
    _recent["checked_at"] = datetime.now(timezone.utc).isoformat()


def _get_client():
    global _client
    if _client is None:
        if not settings.llm_enabled:
            raise LLMError("not_configured", "LLM_API_KEY / LLM_BASE_URL 未配置", is_retryable=False)
        from openai import OpenAI
        _client = OpenAI(base_url=settings.llm_base_url,
                         api_key=settings.llm_api_key,
                         timeout=settings.llm_timeout_seconds)
    return _client


_client = None


def complete(messages: list, temperature: float = 0.3) -> dict:
    """单轮补全。返回 {content, usage, model, finish_reason}；失败抛 LLMError。"""
    resp = _request(messages, temperature=temperature)
    return {
        "content": resp["content"],
        "usage": resp["usage"],
        "model": resp["model"],
        "finish_reason": resp["finish_reason"],
    }


def complete_with_tools(messages: list, tools: list, temperature: float = 0.2,
                        timeout: float | None = None, max_tokens: int | None = None,
                        thinking: bool | None = None) -> dict:
    """带原生工具调用的补全。返回 {content, tool_calls, usage, model, finish_reason}。

    tool_calls 为 OpenAI 协议原始结构 [{id, type, function:{name, arguments}}]，
    参数校验由工具注册表完成，此处不做任何静默修复。
    timeout：本次调用的时限（秒），由引擎按 run 剩余时限传入；缺省用 llm_timeout_seconds。
    tools 为空列表时不声明工具（多 Agent 角色的结构化分析走这里，保持唯一网络边界）。
    max_tokens：单次输出上限，缺省用 llm_max_tokens_per_request（角色按 agents.yaml 配置）。
    thinking：是否开启模型推理模式；None 不传参数，沿用接口默认（开启）。
    """
    resp = _request(messages, temperature=temperature, tools=tools, tool_choice="auto",
                    timeout=timeout, max_tokens=max_tokens, thinking=thinking)
    return {
        "content": resp["content"],
        "tool_calls": resp["tool_calls"],
        "usage": resp["usage"],
        "model": resp["model"],
        "finish_reason": resp["finish_reason"],
    }


def complete_json(messages: list, temperature: float = 0.1) -> object:
    """结构化 JSON 输出。失败抛 LLMError（含解析失败），不返回预存内容。"""
    result = complete(messages, temperature=temperature)
    text = (result["content"] or "").strip()
    if text.startswith("```"):
        # 容错剥离 markdown 围栏；仍解析失败则抛错，不伪造数据
        text = text.split("```")[1].removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError("bad_json", f"模型输出无法解析为 JSON: {exc}", is_retryable=True) from exc


def _request(messages: list, *, temperature: float, tools: list | None = None,
             tool_choice: str = "auto", timeout: float | None = None,
             max_tokens: int | None = None, thinking: bool | None = None) -> dict:
    """统一请求入口：超时与异常类型化，耗时与 usage 一并返回。

    @why 传入 timeout 时关闭 SDK 自动重试：重试会让单次调用耗时成倍超出
         run 剩余时限；是否重试由引擎按时限决定。
    @why thinking=False 时显式传 {"thinking": {"type": "disabled"}}：DeepSeek 默认开启推理，
         推理 token 计入输出上限且占大半耗时。结论数字由规则工具算出、事实校验兜底，
         写解读和报告不依赖长推理（2026-10-24 实测报告首调 41s，8192 上限仍被截断）。
    """
    if not settings.llm_enabled:
        _note("not_configured", "not_configured")
        raise LLMError("not_configured", "LLM_API_KEY / LLM_BASE_URL 未配置", is_retryable=False)
    started = time.monotonic()
    kwargs = dict(
        model=settings.llm_api_model, messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or settings.llm_max_tokens_per_request)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice
    if thinking is not None:
        kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}
    effective_timeout = timeout if timeout is not None else settings.llm_timeout_seconds
    try:
        client = _get_client()
        if timeout is not None:
            client = client.with_options(timeout=timeout, max_retries=0)
        resp = client.chat.completions.create(**kwargs)
    except LLMError:
        raise
    except Exception as exc:  # openai SDK 各类异常统一类型化
        err = _to_llm_error(exc, effective_timeout)
        _note("error", err.code)
        raise err from exc
    _note("ok")

    choice = resp.choices[0]
    message = choice.message
    usage = getattr(resp, "usage", None)
    return {
        "content": message.content,
        "tool_calls": [tc.model_dump() for tc in (message.tool_calls or [])],
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        },
        "model": resp.model or settings.llm_model,
        "finish_reason": choice.finish_reason,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _to_llm_error(exc: Exception, timeout_seconds: float | None = None) -> LLMError:
    """@why 优先按 HTTP 状态码分类，不再匹配错误文本：文本里的 request_id 等随机串
    可能恰好含 "429" 之类的数字，曾把 400 误判成限流。"""
    name = type(exc).__name__
    message = str(exc)
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return LLMError("auth_failed", "模型鉴权失败，请检查 LLM_API_KEY", is_retryable=False)
    if status == 429:
        return LLMError("rate_limited", "模型限流，请稍后重试", is_retryable=True)
    if status in (400, 404, 422):
        # 请求本身有问题（如模型 ID 不被接口接受），重试无意义；保留接口返回的原因便于排查
        return LLMError("bad_request", f"模型接口拒绝请求（HTTP {status}）: {message[:300]}",
                        is_retryable=False)
    if status is None and "timeout" in name.lower():
        limit = timeout_seconds if timeout_seconds is not None else settings.llm_timeout_seconds
        return LLMError("timeout", f"模型请求超时（{limit:g}s）", is_retryable=True)
    if status is None and "connection" in name.lower():
        return LLMError("unavailable", f"无法连接模型服务: {message[:200]}", is_retryable=True)
    return LLMError("unavailable", f"模型服务不可用: {name}: {message[:200]}", is_retryable=True)
