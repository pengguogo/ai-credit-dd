"""执行状态与工具契约 — 设计文档 §4 状态机 / §7 ToolResult 的纯类型定义。"""
from dataclasses import dataclass, field


# run 终态与运行态（设计 §4）
RUNNING = "running"
SUCCEEDED = "succeeded"
NEEDS_CONFIRMATION = "needs_confirmation"
NEEDS_CLARIFICATION = "needs_clarification"
BLOCKED = "blocked"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
FAILED = "failed"

TERMINAL_STATUSES = {SUCCEEDED, NEEDS_CONFIRMATION, NEEDS_CLARIFICATION,
                     BLOCKED, INSUFFICIENT_EVIDENCE, FAILED}


@dataclass
class ToolResultError:
    code: str
    message: str
    is_retryable: bool = False


@dataclass
class ToolResult:
    """统一内部工具返回（设计 §7）：data 必须可 JSON 序列化。"""

    is_success: bool
    data: object = None
    evidence_ids: list[str] = field(default_factory=list)
    error: ToolResultError | None = None

    @staticmethod
    def success(data: object, evidence_ids: list[str] | None = None) -> "ToolResult":
        return ToolResult(is_success=True, data=data, evidence_ids=evidence_ids or [])

    @staticmethod
    def failure(code: str, message: str, is_retryable: bool = False) -> "ToolResult":
        return ToolResult(is_success=False, error=ToolResultError(
            code=code, message=message, is_retryable=is_retryable))


@dataclass
class EvidenceRecord:
    """工具执行时产出的证据描述，由服务层持久化为 evidence 表行。

    @why source_ref 必须含表/主键或文档 ID（设计 §6）：只有 SQL 文本不足以复核。
    """

    source_type: str          # db_query | document | calculation
    source_ref: dict          # {table, keys, filters} 或 {docId}
    snapshot: object          # 当次结果快照（行/片段）
    data_version: int
