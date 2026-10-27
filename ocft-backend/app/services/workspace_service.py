"""报告列表：尽调产出物的建档与检索。

@why 报告本身不需要状态：确认 / 驳回 / 归档这套流转已去掉，审核结论记在贷款申请
      （loan_application.status：待处理 → 待审核 → 审核通过 / 审核不通过），报告只表示
      「这次 run 产出了一份报告」。正文不复制，档案只用 runId 指向原报告与证据，
      避免同一结论出现两个版本。
"""
from __future__ import annotations

import hashlib
import math
import uuid

from sqlalchemy.orm import Session

from ..api_errors import ApiError
from ..models import AgentRun, EnterpriseBasic, Evidence, LoanApplication, WorkspaceAsset
from .run_service import iso_z


def _new_id() -> str:
    return "ast_" + uuid.uuid4().hex[:12]


def _summary(answer: str | None) -> str | None:
    """从正文里取「尽调结论」一句作为档案摘要；没有时退回正文前 160 字。"""
    text = (answer or "").strip()
    if not text:
        return None
    for line in text.splitlines():
        clean = line.strip().lstrip("-").replace("**", "").strip()
        if "尽调结论" in clean:
            return clean[:180]
    head = " ".join(text.replace("#", " ").replace("**", "").split())
    return head[:160] or None


def _title(application_id: str | None, enterprise_id: str | None, scope: str = "loan") -> str:
    if application_id:
        return f"{application_id} 企业信贷尽调报告"
    if enterprise_id:
        return f"{enterprise_id} 企业主体尽调报告" if scope == "enterprise" else f"{enterprise_id} 企业信贷尽调报告"
    return "企业信贷尽调报告"


def _report_target(db: Session, run) -> tuple[str | None, str | None, str]:
    """报告口径与对象：优先取本次 build_dd_report 证据快照，而不是会话实体槽位。

    @why 主控定位阶段可能先调 find_enterprise，实体里会带上该企业唯一的一笔申请；
         企业口径报告的正文与证据都没有申请编号，档案不能因为定位痕迹被挂到那笔贷款上。
    """
    rows = (db.query(Evidence).filter(Evidence.run_id == run.id)
            .order_by(Evidence.created_at.desc(), Evidence.id.desc()).all())
    for evidence in rows:
        if (evidence.source_ref or {}).get("calc") != "build_dd_report":
            continue
        snapshot = evidence.snapshot if isinstance(evidence.snapshot, dict) else {}
        scope = "enterprise" if snapshot.get("scope") == "enterprise" else "loan"
        return snapshot.get("applicationId") or None, snapshot.get("enterpriseId") or None, scope
    entities = (run.context_snapshot or {}).get("entities") or {}
    application_id = next((items[0] for key, items in entities.items()
                           if key == "applicationId" and items), None)
    enterprise_id = next((items[0] for key, items in entities.items()
                          if key == "enterpriseId" and items), None)
    return application_id, enterprise_id, "loan"


# 完整尽调报告：贷款口径五部分、企业口径四部分都算产出物；追问答案与澄清不是资产
REPORT_MARKERS = ("## 企业概况", "## 财务分析", "## 风险提示")
REPORT_TAIL_MARKERS = ("## 额度建议", "## 风控条件")


def _advance_application(db: Session, application_id: str | None) -> None:
    """生成尽调报告后，申请从「待处理」推进到「待审核」。

    @why 只有仍处于待处理（尚未审核）的申请才推进；已审核通过 / 审核不通过的不覆盖人工结论。
    """
    if not application_id:
        return
    loan = (db.query(LoanApplication)
            .filter(LoanApplication.application_id == application_id).first())
    if loan is not None and (loan.status or "pending") == "pending":
        loan.status = "pending_review"


def register_asset(db: Session, run, actor_id: str) -> WorkspaceAsset | None:
    """run 完成后建档（同一 run 只建一次），并把该申请的贷款状态推进到待审核。

    @why 只在有完整报告的终态建档：贷款口径五部分（含额度建议）、企业口径四部分（含风控条件）
         都算产出物；追问、失败、澄清不制造空档案；证据条数取本次 run 实际落库数，供检索时判断材料是否齐全。
    @why status / version 是历史列，保留默认值只为兼容既有库，不再对外暴露。
    """
    existing = db.query(WorkspaceAsset).filter(WorkspaceAsset.run_id == run.id).first()
    if existing is not None:
        return existing
    answer = run.answer or ""
    if not (all(marker in answer for marker in REPORT_MARKERS)
            and any(marker in answer for marker in REPORT_TAIL_MARKERS)):
        return None
    application_id, enterprise_id, scope = _report_target(db, run)
    evidence_count = db.query(Evidence).filter(Evidence.run_id == run.id).count()
    asset = WorkspaceAsset(
        id=_new_id(), scenario_id=run.scenario_id,
        application_id=application_id, enterprise_id=enterprise_id,
        conversation_id=run.conversation_id, run_id=run.id, kind="report",
        title=_title(application_id, enterprise_id, scope),
        summary=_summary(run.answer),
        evidence_count=evidence_count,
        content_sha256=hashlib.sha256(run.answer.encode("utf-8")).hexdigest(),
        created_by=actor_id,
    )
    db.add(asset)
    _advance_application(db, application_id)
    return asset


def _report_metadata(db: Session, run_ids: list[str]) -> dict[str, dict]:
    """批量读取当次报告元信息，不用当前贷款数据覆盖历史快照。"""
    if not run_ids:
        return {}
    metadata = {run_id: {"reportGeneratedAt": iso_z(finished_at)}
                for run_id, finished_at in db.query(AgentRun.id, AgentRun.finished_at)
                .filter(AgentRun.id.in_(run_ids)).all()}
    priorities: dict[str, int] = {}
    rows = (db.query(Evidence).filter(Evidence.run_id.in_(run_ids))
            .order_by(Evidence.created_at, Evidence.id).all())
    for evidence in rows:
        calc = (evidence.source_ref or {}).get("calc")
        snapshot = evidence.snapshot
        if not isinstance(snapshot, dict):
            continue
        if calc == "build_dd_report":
            credit = snapshot.get("creditSuggestion")
            amount = credit.get("applyAmount") if isinstance(credit, dict) else None
            priority = 2
        elif calc == "calc_credit_limit":
            amount = snapshot.get("applyAmount")
            priority = 1
        else:
            continue
        if (isinstance(amount, (int, float)) and not isinstance(amount, bool)
                and math.isfinite(amount) and amount >= 0
                and priority >= priorities.get(evidence.run_id, 0)):
            metadata.setdefault(evidence.run_id, {})["applyAmount"] = amount
            priorities[evidence.run_id] = priority
    return metadata


def _asset_out(asset: WorkspaceAsset, enterprise_name: str | None, metadata: dict) -> dict:
    return {
        "id": asset.id, "scenarioId": asset.scenario_id,
        "applicationId": asset.application_id, "enterpriseId": asset.enterprise_id,
        "enterpriseName": enterprise_name,
        "applyAmount": metadata.get("applyAmount"),
        "reportGeneratedAt": metadata.get("reportGeneratedAt") or iso_z(asset.created_at) or "",
        "conversationId": asset.conversation_id, "runId": asset.run_id,
        "kind": asset.kind, "title": asset.title,
        "summary": asset.summary,
        "evidenceCount": asset.evidence_count,
        "contentSha256": asset.content_sha256,
        "createdBy": asset.created_by,
        "createdAt": iso_z(asset.created_at) or "",
        "updatedAt": iso_z(asset.updated_at) or "",
    }


def list_assets(db: Session, *, keyword: str | None = None,
                application_id: str | None = None, enterprise_id: str | None = None,
                kind: str | None = None, limit: int = 30, offset: int = 0) -> dict:
    # 读取时关联企业事实：旧档案也有中文名称，资料缺失不丢失档案。
    query = (db.query(WorkspaceAsset, EnterpriseBasic.enterprise_name)
             .outerjoin(EnterpriseBasic, WorkspaceAsset.enterprise_id == EnterpriseBasic.enterprise_id))
    if application_id:
        query = query.filter(WorkspaceAsset.application_id == application_id)
    if enterprise_id:
        query = query.filter(WorkspaceAsset.enterprise_id == enterprise_id)
    if kind:
        query = query.filter(WorkspaceAsset.kind == kind)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(WorkspaceAsset.title.like(like)
                             | EnterpriseBasic.enterprise_name.like(like)
                             | WorkspaceAsset.application_id.like(like)
                             | WorkspaceAsset.enterprise_id.like(like)
                             | WorkspaceAsset.summary.like(like))
    total = query.count()
    rows = (query.order_by(WorkspaceAsset.created_at.desc())
            .offset(offset).limit(limit).all())
    metadata = _report_metadata(db, [asset.run_id for asset, _name in rows])
    return {"assets": [_asset_out(asset, name, metadata.get(asset.run_id, {})) for asset, name in rows],
            "total": total,
            "limit": limit, "offset": offset, "hasMore": offset + len(rows) < total}


def view_asset(db: Session, asset_id: str) -> dict:
    row = (db.query(WorkspaceAsset, EnterpriseBasic.enterprise_name)
           .outerjoin(EnterpriseBasic, WorkspaceAsset.enterprise_id == EnterpriseBasic.enterprise_id)
           .filter(WorkspaceAsset.id == asset_id).first())
    if row is None:
        raise ApiError(404, "not_found", "报告不存在")
    asset, enterprise_name = row
    metadata = _report_metadata(db, [asset.run_id]).get(asset.run_id, {})
    return _asset_out(asset, enterprise_name, metadata)
