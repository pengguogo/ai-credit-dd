"""评测 Runner — 逐题走统一答题入口，断点续跑，汇总并导出。

用法（cwd=ocft-backend）：
    python -m eval.run --input eval/datasets/public_sample.jsonl
    python -m eval.run --input hidden.jsonl --export-format default   # 非公开题：只跑不评
    参数：--output-dir 输出目录  --fresh 忽略已有结果从头跑  --limit N 只跑前 N 题
          --skip-leak-check 跳过泄漏检查（不建议）

@why 唯一 pipeline：直接调用 run_service.create_run，与 HTTP / 前端完全同一路径；
     Agent 只拿到问题文本，expected 只在本进程内交给 scoring。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from eval.dataset import DatasetError, Item, load_dataset  # noqa: E402
from eval.leak_check import find_leaks  # noqa: E402
from eval.scoring import score  # noqa: E402
from eval.table_export import write_csv, write_xlsx  # noqa: E402

EVAL_ACTOR = "eval_runner"
SNAPSHOT_LIMIT = 300  # 结果文件里证据快照只保留摘要，完整快照在 evidence 表


# ---- 导出格式：官方格式公布后在此新增适配器 ----

def _export_default(results: list[dict]) -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(results),
        "answers": [{
            "id": r["id"],
            "status": r["status"],
            "answer": r.get("answer") or r.get("errorMessage") or "",
            "evidence": [{"id": e["id"], "source": e["source"]} for e in r.get("evidence", [])],
            "runIds": r.get("runIds", []),
        } for r in results],
    }


EXPORTERS: dict[str, Callable[[list[dict]], object]] = {"default": _export_default}


# ---- 单题执行 ----

def run_item(item: Item) -> dict:
    """执行一道题（多轮题在同一会话依次提问），返回结果行。异常被捕获并记为 runner_error。"""
    from app.db import SessionLocal
    from app.agent.scenarios import DEFAULT_SCENARIO_ID
    from app.models import Evidence
    from app.services import run_service
    from app.services.run_service import masked_snapshot, masked_source_ref

    started = time.monotonic()
    row: dict = {"id": item.id, "turns": len(item.turns), "questions": list(item.turns),
                 "scenarioId": item.scenario_id or DEFAULT_SCENARIO_ID, "runIds": [], "toolNames": [],
                 "evidence": [], "usage": {"promptTokens": 0, "completionTokens": 0, "totalTokens": 0}}
    conversation_id = None
    try:
        with SessionLocal() as db:
            for question in item.turns:
                run = run_service.create_run(
                    db, question=question, conversation_id=conversation_id,
                    scenario_id=item.scenario_id or DEFAULT_SCENARIO_ID, actor_id=EVAL_ACTOR)
                conversation_id = run.conversation_id
                _, traces, evidence_ids = run_service.get_run(db, run.id, EVAL_ACTOR)
                row["runIds"].append(run.id)
                row["toolNames"] += [t.tool_name for t in traces]
                for key in row["usage"]:
                    row["usage"][key] += (run.usage or {}).get(key, 0)
                for ev in db.query(Evidence).filter(Evidence.id.in_(evidence_ids)).order_by(Evidence.id):
                    row["evidence"].append({
                        # 导出文件同样脱敏（待办 0-7，自查第 10 条）
                        "id": ev.id, "source": masked_source_ref(ev), "sourceType": ev.source_type,
                        "contentHash": ev.content_hash,
                        "snapshot": json.dumps(masked_snapshot(ev), ensure_ascii=False,
                                               default=str)[:SNAPSHOT_LIMIT],
                    })
            row.update(status=run.status, answer=run.answer, errorCode=run.error_code,
                       errorMessage=run.error_message, conversationId=conversation_id)
    except Exception as exc:  # 单题失败不影响整批
        row.update(status="runner_error", answer=None, errorCode="runner_error",
                   errorMessage=f"{type(exc).__name__}: {exc}"[:500])
    row["durationMs"] = int((time.monotonic() - started) * 1000)
    return row


# ---- 批量执行 ----

def _safe_log(message: str) -> None:
    """控制台编码不是 UTF-8（如 Windows GBK）时，去掉无法编码的符号再打印。"""
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(message.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def evaluate(input_path: str | Path, output_dir: str | Path | None = None, *, fresh: bool = False,
             limit: int | None = None, export_format: str = "default", leak_check: bool = True,
             log: Callable[[str], None] = _safe_log) -> dict:
    items, expected = load_dataset(input_path)
    if limit:
        items = items[:limit]
    if export_format not in EXPORTERS:
        raise DatasetError(f"未知导出格式 {export_format}，可用 {sorted(EXPORTERS)}")
    if leak_check:
        leaks = find_leaks(items, expected, [BACKEND_ROOT / "app"])
        if leaks:
            raise DatasetError("泄漏检查未通过（红线 R5）：\n" + "\n".join(leaks))

    out = Path(output_dir) if output_dir else BACKEND_ROOT / "eval" / "output" / Path(input_path).stem
    out.mkdir(parents=True, exist_ok=True)
    results_path = out / "results.jsonl"
    if fresh and results_path.exists():
        results_path.unlink()

    _prepare_database()
    done = _load_done(results_path)
    log(f"题目 {len(items)} 道，已完成 {len(done)} 道，输出到 {out}")
    with results_path.open("a", encoding="utf-8") as fh:
        for index, item in enumerate(items, 1):
            if item.id in done:
                continue
            row = run_item(item)
            row["eval"] = score(row, expected.get(item.id))
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            fh.flush()
            done[item.id] = row
            mark = "" if row["eval"] is None else (" ✓" if row["eval"]["passed"] else " ✗")
            log(f"[{index}/{len(items)}] {item.id} {row['status']} {row['durationMs']}ms{mark}")

    results = [done[i.id] for i in items if i.id in done]
    summary = summarize(results, input_path)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "answers.json").write_text(
        json.dumps(EXPORTERS[export_format](results), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    write_csv(results, out / "results.csv")
    write_xlsx(results, out / "results.xlsx")
    _log_summary(summary, log)
    log(f"结果表格：{out / 'results.csv'}、{out / 'results.xlsx'}")
    return summary


def summarize(results: list[dict], input_path: str | Path) -> dict:
    statuses: dict[str, int] = {}
    error_codes: dict[str, int] = {}
    for r in results:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        if r.get("errorCode"):
            error_codes[r["errorCode"]] = error_codes.get(r["errorCode"], 0) + 1
    scored = [r for r in results if r.get("eval")]
    answered = [r for r in results if r.get("answer")]
    return {
        "input": str(input_path),
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(results),
        "statuses": statuses,
        "errorCodes": error_codes,
        "scored": len(scored),
        "accuracy": round(sum(r["eval"]["passed"] for r in scored) / len(scored), 4) if scored else None,
        "meanScore": round(sum(r["eval"]["score"] for r in scored) / len(scored), 4) if scored else None,
        "answersWithoutEvidence": sum(1 for r in answered if not r.get("evidence")),
        "avgDurationMs": int(sum(r["durationMs"] for r in results) / len(results)) if results else 0,
        "totalTokens": sum(r["usage"]["totalTokens"] for r in results),
        "failures": [{
            "id": r["id"], "status": r["status"], "errorCode": r.get("errorCode"),
            "failedChecks": [c["name"] + "：" + c["detail"] for c in r["eval"]["checks"] if not c["passed"]],
        } for r in scored if not r["eval"]["passed"]],
    }


def _prepare_database() -> None:
    from app.config import settings
    from app.db import init_db, seed_business_data
    settings.validate_runtime()
    init_db()
    seed_business_data()


def _load_done(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                done[row["id"]] = row
    return done


def _log_summary(summary: dict, log: Callable[[str], None]) -> None:
    log(f"完成 {summary['total']} 道：{summary['statuses']}")
    if summary["accuracy"] is not None:
        log(f"正确率 {summary['accuracy']:.1%}（{summary['scored']} 道有期望），平均分 {summary['meanScore']:.2f}")
    log(f"无证据答案 {summary['answersWithoutEvidence']} 道，平均耗时 {summary['avgDurationMs']}ms，"
        f"总 token {summary['totalTokens']}")
    for f in summary["failures"]:
        log(f"  ✗ {f['id']} [{f['status']}] " + "；".join(f["failedChecks"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCFT Agent 评测")
    parser.add_argument("--input", required=True,
                        help="题目文件（.jsonl / .json / .csv / .xlsx）或包含这些文件的目录")
    parser.add_argument("--output-dir")
    parser.add_argument("--fresh", action="store_true", help="忽略已有结果，从头跑")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--export-format", default="default", choices=sorted(EXPORTERS))
    parser.add_argument("--skip-leak-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        evaluate(args.input, args.output_dir, fresh=args.fresh, limit=args.limit,
                 export_format=args.export_format, leak_check=not args.skip_leak_check)
    except DatasetError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
