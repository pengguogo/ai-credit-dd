"""工具注册表 — 声明 / 校验 / 分发（设计 §5）。

@why LLM tool_calls.arguments 是原始 JSON 字符串：必须显式解析与校验，
     未知参数、类型不符直接拒绝（invalid_args），不静默忽略或修复——
     防参数漂移与幻觉注入。工具函数本体保持纯逻辑可单测。
"""
import json
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from ..domain.errors import ToolError
from ..domain.types import EvidenceRecord, ToolResult

# handler 形参名用 camelCase：与 LLM 协议参数名一致（系统边界适配，见工具实现文件）
ToolHandler = Callable[..., "tuple[ToolResult, list[EvidenceRecord], dict]"]
# 返回：(给 LLM 的 ToolResult, 待持久化证据, 已解析参数)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON Schema，属性名 camelCase
    handler: ToolHandler


_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(name: str, description: str, parameters: dict) -> Callable:
    def decorator(fn: ToolHandler) -> ToolHandler:
        if name in _REGISTRY:
            raise ValueError(f"工具重复注册: {name}")
        _REGISTRY[name] = ToolSpec(name=name, description=description,
                                   parameters=parameters, handler=fn)
        return fn
    return decorator


def list_tool_names() -> list[str]:
    return list(_REGISTRY)


def get_openai_tools(allowed: list[str]) -> list[dict]:
    """按场景输出 OpenAI tools 协议声明；未注册名 fail-fast。"""
    out: list[dict] = []
    for name in allowed:
        spec = _REGISTRY.get(name)
        if spec is None:
            raise ToolError("not_allowed", f"未注册的工具: {name}")
        out.append({
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        })
    return out


def execute_tool(db: Session, run_ctx: dict, name: str,
                 arguments_json: str) -> tuple[ToolResult, list[EvidenceRecord], dict]:
    """校验并执行一次工具调用；任何失败类型化为 ToolResult.failure，不向上抛。"""
    spec = _REGISTRY.get(name)
    if spec is None:
        return ToolResult.failure("not_allowed", f"工具 {name} 未注册或当前场景不可用"), [], {}
    try:
        args = _parse_and_validate(spec, arguments_json)
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message), [], {}
    try:
        return spec.handler(db=db, run_ctx=run_ctx, **args)
    except ToolError as exc:
        return ToolResult.failure(exc.code, exc.message, exc.is_retryable), [], args
    except Exception as exc:  # 工具内部意外异常：可见不吞，落 trace 供排查
        return ToolResult.failure("execution_failed", f"{type(exc).__name__}: {exc}"), [], args


_TYPE_MAP = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


def _parse_and_validate(spec: ToolSpec, arguments_json: str) -> dict:
    text = (arguments_json or "").strip()
    if not text:
        args: dict = {}
    else:
        try:
            args = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolError("invalid_args", f"参数不是合法 JSON: {exc}") from exc
    if not isinstance(args, dict):
        raise ToolError("invalid_args", "参数必须是 JSON 对象")
    props = spec.parameters.get("properties", {})
    unknown = set(args) - set(props)
    if unknown:
        raise ToolError("invalid_args", f"未知参数: {', '.join(sorted(unknown))}")
    for key in spec.parameters.get("required", []):
        if args.get(key) in (None, ""):
            raise ToolError("invalid_args", f"缺少必填参数: {key}")
    for key, value in args.items():
        _check_type(key, value, props.get(key, {}).get("type"))
    return args


def _check_type(key: str, value, expected: str | None) -> None:
    if expected not in _TYPE_MAP or value is None:
        return
    # bool 是 int 子类，显式排除整数场景误判
    if expected in ("integer", "number") and isinstance(value, bool):
        raise ToolError("invalid_args", f"参数 {key} 需要 {expected} 类型")
    if not isinstance(value, _TYPE_MAP[expected]):
        raise ToolError("invalid_args", f"参数 {key} 需要 {expected} 类型")
