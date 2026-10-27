"""赛题 04 准备工具：合成数据验证隔离、格式失败和数据异常，不含标准答案。"""
import csv
import json
from pathlib import Path

import pytest

from eval.dataset import DatasetError, load_dataset
from eval.dd04 import RESULT_COLUMNS, prepare_inputs, validate_results
from eval.dd04_data import SCHEMAS, audit_data


def write_csv(path, header, rows, encoding="utf-8-sig"):
    with path.open("w", encoding=encoding, newline="") as stream:
        csv.writer(stream).writerows([header, *rows])
    return path


@pytest.mark.parametrize("kind,key", [("applications", "application_id"), ("questions", "question_id")])
def test_answer_changes_never_reach_agent_request(tmp_path, monkeypatch, kind, key):
    from app.services import run_service
    from eval.run import run_item

    requests = []

    def capture(_db, **kwargs):
        requests.append(kwargs)
        raise RuntimeError("测试只捕获 Agent 请求，不执行模型")

    monkeypatch.setattr(run_service, "create_run", capture)
    path = tmp_path / "input.csv"
    prepared = []
    for marker in ("REFERENCE_SECRET_ALPHA", "REFERENCE_SECRET_BETA"):
        write_csv(path, [key, "enterprise_id", "question", "reference_answer", "expected", "risk_level"],
                  [["SYN-1", "SYN-E", "请提供财务依据", marker, marker, marker]])
        items = prepare_inputs(path, kind, "synthetic_scene")
        prepared.append(items)
        clean = tmp_path / "clean.jsonl"
        clean.write_text(json.dumps(items[0], ensure_ascii=False) + "\n", encoding="utf-8")
        loaded, expected = load_dataset(clean)
        assert expected == {}
        run_item(loaded[0])
    assert prepared[0] == prepared[1]
    assert requests[0] == requests[1]
    assert "SYN-E" in requests[0]["question"]
    assert "REFERENCE_SECRET" not in json.dumps(requests)
    assert set(prepared[0][0]) == {"id", "question", "scenarioId"}


@pytest.mark.parametrize("rows", [
    [["", "SYN-E", "问询"]],
    [["SYN-1", "", "问询"]],
    [["SYN-1", "SYN-E", "问询"], ["SYN-1", "SYN-E", "问询"]],
])
def test_prepare_rejects_invalid_identifiers(tmp_path, rows):
    path = write_csv(tmp_path / "q.csv", ["question_id", "enterprise_id", "question"], rows)
    with pytest.raises(DatasetError):
        prepare_inputs(path, "questions", "synthetic_scene")


def result_files(tmp_path):
    inputs = write_csv(tmp_path / "applications.csv", ["application_id", "enterprise_id"], [["SYN-1", "SYN-E"]])
    # 全部为占位文本；校验器不验证业务正确性，不把这些数据作为系统答案。
    row = ["SYN-1", "SYN-E", "合成评级", "合成额度", "合成结论", "合成要点"]
    results = write_csv(tmp_path / "results.csv", RESULT_COLUMNS, [row])
    return inputs, results, row


def test_valid_format_is_not_a_business_score(tmp_path):
    inputs, results, _ = result_files(tmp_path)
    report = validate_results(inputs, results)
    assert report["passed"] and report["actualCount"] == 1
    assert "不代表业务正确" in report["scope"]


@pytest.mark.parametrize("fault,code", [
    ("duplicate", "duplicate"), ("missing", "missing"),
    ("wrong_enterprise", "enterprise_mismatch"), ("empty", "empty_field"),
    ("encoding", "encoding"), ("extra_column", "columns"),
])
def test_bad_results_fail(tmp_path, fault, code):
    inputs, results, row = result_files(tmp_path)
    header = list(RESULT_COLUMNS)
    rows = [row]
    if fault == "duplicate":
        rows.append(row[:])
    elif fault == "missing":
        row[0] = "SYN-OTHER"
    elif fault == "wrong_enterprise":
        row[1] = "SYN-OTHER"
    elif fault == "empty":
        row[3] = ""
    elif fault == "extra_column":
        header.append("status")
        row.append("failed")
    write_csv(results, header, rows, "utf-8" if fault == "encoding" else "utf-8-sig")
    report = validate_results(inputs, results)
    assert not report["passed"]
    assert code in {e["code"] for e in report["errors"]}


def test_missing_column_and_malformed_row_rejected(tmp_path):
    inputs, results, row = result_files(tmp_path)
    for header, values in [(RESULT_COLUMNS[:-1], row[:-1]), (RESULT_COLUMNS, row[:-1])]:
        write_csv(results, header, [values])
        with pytest.raises(DatasetError):
            validate_results(inputs, results)


@pytest.mark.parametrize("valid", [True, False])
def test_validation_cli_exit_status(tmp_path, monkeypatch, capsys, valid):
    from eval.dd04 import main

    inputs, results, row = result_files(tmp_path)
    if not valid:
        row[3] = ""
        write_csv(results, RESULT_COLUMNS, [row])
    monkeypatch.setattr("sys.argv", ["dd04", "validate", "--applications", str(inputs),
                                     "--results", str(results)])
    assert main() == (0 if valid else 1)
    assert json.loads(capsys.readouterr().out)["passed"] is valid


def test_data_audit_finds_corruption_without_opening_labels(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[2] / "docs/00-rules/赛题/赛题04_企业智能信贷尽调/data"
    # 只复制业务与关系表；测试目录里根本不存在答案文件。
    for table in (*SCHEMAS, "schema_relationships"):
        (tmp_path / f"{table}.csv").write_bytes((source / f"{table}.csv").read_bytes())
    baseline = audit_data(tmp_path)
    assert baseline["passed"]
    finance = tmp_path / "enterprise_finance.csv"
    with finance.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["revenue"] = "NaN"
    rows[0]["enterprise_id"] = "SYN-ORPHAN"
    rows[0]["total_assets"] = "999999999"
    rows.append(rows[0].copy())
    write_csv(finance, SCHEMAS["enterprise_finance"], [[r[k] for k in SCHEMAS["enterprise_finance"]] for r in rows])
    # 禁止读取白名单外的 CSV，即使未来添加文件发现逻辑也会触发测试。
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path.suffix == ".csv":
            assert path.stem in {*SCHEMAS, "schema_relationships"}
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    report = audit_data(tmp_path)
    assert not report["passed"]
    assert {"invalid_number", "orphan_enterprise", "balance_mismatch", "duplicate_key", "three_years_incomplete"} <= {i["code"] for i in report["issues"]}
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_export_includes_pending_confirmation_and_marks_failures(tmp_path):
    """官方六列导出：needs_confirmation 是已出结论，照常导出并在状态清单标待确认；失败如实写明。"""
    from eval.dd04 import export_results

    inputs = write_csv(tmp_path / "applications.csv", ["application_id", "enterprise_id"],
                       [["SYN-1", "SYN-E1"], ["SYN-2", "SYN-E2"], ["SYN-3", "SYN-E3"]])
    runs = tmp_path / "results.jsonl"
    runs.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in [
        {"id": "SYN-1", "status": "succeeded", "runIds": ["run-1"]},
        {"id": "SYN-2", "status": "needs_confirmation", "runIds": ["run-2"], "answer": "完整报告：合成企业概况、财务、风险、额度和风控条件。"},
        {"id": "SYN-3", "status": "failed", "errorCode": "llm_unavailable", "runIds": ["run-3"]},
    ]), encoding="utf-8")

    def loader(run_ids):
        # 合成证据：只验证取数与导出口径，不代表任何真实结论
        return [{"sourceRef": {"calc": "build_dd_report"},
                 "snapshot": json.dumps({"riskLevel": "合成档位", "suggestedCreditAmount": "100-200",
                                         "dueDiligenceConclusion": f"合成结论 {run_ids[0]}",
                                         "scoringPoints": ["合成要点A", "合成要点B"]})}]

    output = tmp_path / "out" / "official.csv"
    summary = export_results(inputs, runs, output, evidence_loader=loader)
    assert summary["concluded"] == 2 and summary["notConcluded"] == 1
    assert summary["pendingConfirmation"] == ["SYN-2"]
    assert validate_results(inputs, output)["passed"]
    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = {row["application_id"]: row for row in csv.DictReader(stream)}
    assert rows["SYN-2"]["scoring_points"] == "合成要点A;合成要点B"
    assert rows["SYN-2"]["due_diligence_conclusion"] == "完整报告：合成企业概况、财务、风险、额度和风控条件。"
    assert rows["SYN-3"]["risk_level"].startswith("未生成结论（failed/llm_unavailable")
    with (tmp_path / "out" / "official-status.csv").open(encoding="utf-8-sig", newline="") as stream:
        status = {row["application_id"]: row for row in csv.DictReader(stream)}
    assert status["SYN-2"]["pending_confirmation"] == "是"
    assert status["SYN-1"]["pending_confirmation"] == "否"


def test_missing_business_file_is_reported(tmp_path):
    report = audit_data(tmp_path)
    assert not report["passed"]
    assert len([i for i in report["issues"] if i["code"] == "table_invalid"]) == 10
