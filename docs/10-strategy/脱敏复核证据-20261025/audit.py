"""待办 A7 脱敏复核：外送模型的完整请求 + 提交用导出文件逐项扫敏感原值。

用法（仓库根目录）：
    ocft-backend\\.venv\\Scripts\\python.exe docs\\10-strategy\\脱敏复核证据-20261025\\audit.py [--no-live]

做两件事：
1. live：在 llm._request 外层截获每一次外送的完整 messages + tools（不是 llm_calls 里的截断预览），
   走与 HTTP / 评测完全相同的 run_service.create_run，跑 3 个真实 run，
   在完整外送文本里搜赛题数据中的敏感原值（企业全称、信用代码、法人、实控人、自然人股东、
   被担保方、关联企业、注册地址、证件号）。
2. files：扫提交会用到的导出文件，查信用代码、证件号、自然人姓名（企业名称按设计在输出中还原，
   不算泄漏；专属自查 14 要求的是信用代码、法人、账号）。
结果写到同目录 audit-result.json；只记录命中的字段类型、所在位置和前后 20 字，不落完整外送内容。
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BACKEND = ROOT / "ocft-backend"
DATA = ROOT / "docs/00-rules/赛题/赛题04_企业智能信贷尽调/data"
ARCHIVE = ROOT / "测试数据/评测/2026-10-25/00e905f"
sys.path.insert(0, str(BACKEND))


def _rows(name: str) -> list[dict]:
    with open(DATA / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sensitive_values() -> dict[str, set[str]]:
    """按类型收集原值。企业类和自然人类分开，输出侧只查自然人与编码类。"""
    out: dict[str, set[str]] = {k: set() for k in (
        "enterprise_name", "credit_code", "legal_person", "legal_person_id",
        "actual_controller", "register_address", "person_shareholder",
        "enterprise_shareholder", "guaranteed_party", "related_enterprise")}
    for r in _rows("enterprise_basic.csv"):
        for k in ("enterprise_name", "credit_code", "legal_person", "legal_person_id",
                  "actual_controller", "register_address"):
            if r[k].strip():
                out[k].add(r[k].strip())
    for r in _rows("enterprise_shareholder.csv"):
        key = "person_shareholder" if r["shareholder_type"] == "自然人股东" else "enterprise_shareholder"
        out[key].add(r["shareholder_name"].strip())
    for r in _rows("enterprise_guarantee.csv"):
        out["guaranteed_party"].add(r["guaranteed_party"].strip())
    for r in _rows("enterprise_related.csv"):
        out["related_enterprise"].add(r["related_enterprise_name"].strip())
    return {k: {v for v in vs if len(v) >= 2} for k, vs in out.items()}


OUTPUT_KINDS = ("credit_code", "legal_person", "legal_person_id", "actual_controller",
                "person_shareholder")


def find_hits(text: str, values: dict[str, set[str]], kinds, where: str) -> list[dict]:
    hits = []
    for kind in kinds:
        for v in values[kind]:
            start = text.find(v)
            while start != -1:
                hits.append({"where": where, "kind": kind, "valueLen": len(v),
                             "context": text[max(0, start - 20): start + len(v) + 20]
                             .replace(v, "【" + kind + "】")})
                start = text.find(v, start + 1)
    return hits


def live(values: dict[str, set[str]]) -> dict:
    from app import llm
    from app.db import SessionLocal
    from app.services import run_service

    captured: list[str] = []
    original = llm._request

    def capture(messages, **kwargs):
        captured.append(json.dumps({"messages": messages, "tools": kwargs.get("tools")},
                                   ensure_ascii=False, default=str))
        return original(messages, **kwargs)

    llm._request = capture
    basic = {r["enterprise_id"]: r for r in _rows("enterprise_basic.csv")}
    e = basic["E001"]
    cases = [
        ("LA001-full-dd", "企业编号：E001。请对贷款申请 LA001 完成企业信贷尽调，并提供结论与证据。"),
        # 用户直接在问题里写企业全称与法人姓名：验证输入侧也会先替换再外送
        ("name-in-question", f"{e['enterprise_name']}的法定代表人{e['legal_person']}有没有失信或限高记录？"
                             f"统一社会信用代码{e['credit_code']}。"),
        # 与公开问询自测集同一输入格式（见 测试数据/评测/2026-10-25/00e905f/inputs/questions.jsonl）
        ("Q003-public-question", "企业编号：E010。该企业是否存在财务异常或欺诈线索？"),
    ]
    runs = []
    try:
        for case_id, question in cases:
            before = len(captured)
            started = time.monotonic()
            with SessionLocal() as db:
                run = run_service.create_run(db, question=question, conversation_id=None,
                                             scenario_id="enterprise_dd", actor_id="eval_runner")
                runs.append({"case": case_id, "runId": run.id, "status": run.status,
                             "llmCalls": len(captured) - before,
                             "seconds": round(time.monotonic() - started, 1)})
    finally:
        llm._request = original
    hits = []
    for i, payload in enumerate(captured):
        hits += find_hits(payload, values, values.keys(), f"llm_request#{i}")
    return {"runs": runs, "requestsCaptured": len(captured),
            "requestChars": sum(len(p) for p in captured), "hits": hits}


def files(values: dict[str, set[str]]) -> dict:
    targets = [p for p in ARCHIVE.rglob("*") if p.suffix in (".csv", ".jsonl", ".json", ".md")
               and p.is_file()]
    hits, scanned = [], []
    for p in targets:
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        rel = p.relative_to(ROOT).as_posix()
        scanned.append(rel)
        hits += find_hits(text, values, OUTPUT_KINDS, rel)
    # 旧归档：只统计命中数，不进提交包
    legacy = {}
    for d in (ROOT / "测试数据/评测/2026-10-24").glob("dd04-multi-agent*"):
        n = 0
        for p in d.rglob("*"):
            if p.is_file() and p.suffix in (".csv", ".jsonl", ".json", ".md"):
                n += len(find_hits(p.read_text(encoding="utf-8-sig", errors="replace"),
                                   values, values.keys(), ""))
        legacy[d.relative_to(ROOT).as_posix()] = n
    return {"scanned": len(scanned), "hits": hits, "legacyHitCounts": legacy}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-live", action="store_true", help="只扫文件，不调真实模型")
    args = parser.parse_args()
    values = sensitive_values()
    result = {"valueCounts": {k: len(v) for k, v in values.items()}}
    if not args.no_live:
        result["live"] = live(values)
    result["files"] = files(values)
    (HERE / "audit-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    live_hits = len(result.get("live", {}).get("hits", []))
    print(json.dumps({"valueCounts": result["valueCounts"],
                      "liveRuns": result.get("live", {}).get("runs"),
                      "liveRequests": result.get("live", {}).get("requestsCaptured"),
                      "liveHits": live_hits,
                      "fileScanned": result["files"]["scanned"],
                      "fileHits": len(result["files"]["hits"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
