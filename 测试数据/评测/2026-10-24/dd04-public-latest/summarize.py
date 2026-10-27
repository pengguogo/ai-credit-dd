"""真实运行完成后只读取证及评分；参考答案不进入 Agent。cwd=ocft-backend。"""
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import csv
import hashlib
import json
import math
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO / 'ocft-backend'))
from app.db import SessionLocal
from app.models import Evidence
from app.agent.dd_snapshot import build_masker
from app.services.run_service import get_run, masked_snapshot, masked_source_ref
from eval.dd04_credit import collect_runs, compare_amounts
from eval.table_export import write_csv as export_csv


def dump(name, data):
    (ROOT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def csv_out(name, rows):
    with (ROOT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


groups = {}
evidence = {}
with SessionLocal() as db:
    masker = build_masker(db)
    for kind in ['applications', 'questions']:
        path = ROOT / kind / 'results.jsonl'
        raw = [json.loads(line) for line in path.read_text().splitlines() if line]
        assert len(raw) == 10 and len({r['id'] for r in raw}) == 10
        for row in raw:
            for rid in row['runIds']:
                run, traces, ids = get_run(db, rid, 'eval_runner')
                evs = db.query(Evidence).filter(Evidence.id.in_(ids)).order_by(Evidence.id).all()
                evidence[rid] = masker.mask_obj({
                    'status': run.status, 'model': run.model, 'answer': run.answer,
                    'errorCode': run.error_code,
                    'traces': [{'tool': t.tool_name, 'status': t.status, 'errorCode': t.error_code} for t in traces],
                    'evidence': [{'id': e.id, 'source': masked_source_ref(e),
                                  'snapshot': masked_snapshot(e)} for e in evs],
                })
        # 归档答案重新代号化，原始发布名称仍可由 runId 在库内追溯。
        rows = masker.mask_obj(raw)
        groups[kind] = rows
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
        export_csv(rows, ROOT / kind / 'results.csv')
        # 合并工作簿由 artifact-tool 从脱敏后的中间数据生成。
        (ROOT / kind / 'results.xlsx').unlink(missing_ok=True)
        answers = ROOT / kind / 'answers.json'
        answers.write_text(json.dumps(masker.mask_obj(json.loads(answers.read_text())), ensure_ascii=False, indent=2), encoding='utf-8')

dump('run-evidence.json', evidence)
actual = collect_runs(ROOT / 'applications/results.jsonl')
for row in actual:
    row.pop('answer', None)
    row.pop('creditEvidence', None)
dump('application-observed.json', actual)

# 证据与运行结果落盘后才打开参考列。
DATA = REPO / 'docs/00-rules/赛题/赛题04_企业智能信贷尽调/data'
refs = list(csv.DictReader((DATA / '公开测试集答案.csv').open(encoding='utf-8-sig')))
comparison, metrics = compare_amounts(actual, refs)
baseline_dir = ROOT.parent / 'dd04-multi-agent-skills'
baseline_rows = list(csv.DictReader((baseline_dir/'application-comparison.csv').open(encoding='utf-8-sig')))
_, baseline_metrics = compare_amounts(baseline_rows, refs)
baseline_summary = json.loads((baseline_dir/'batch-summary.json').read_text())
dump('baseline-comparison.json', {'baselineCode':baseline_summary['codeSha'],
                                'baselineFieldsRescored':baseline_metrics,
                                'currentFields':metrics,
                                'note':'同一严格评级与数值区间口径重新评分；版本不同，不把变化归因于单个改动'})
for row in comparison:
    row['runIds'] = ','.join(row['runIds'])
csv_out('application-comparison.csv', comparison)

question_refs = {r['question_id']: r for r in csv.DictReader((DATA / 'question_public.csv').open(encoding='utf-8-sig'))}
reviews = []
notes = json.loads((ROOT / 'question-notes.json').read_text())
for row in groups['questions']:
    reviews.append({'questionId': row['id'], 'status': row['status'],
                    'question': question_refs[row['id']]['question'], 'answer': row.get('answer') or row.get('errorMessage'),
                    'referenceAnswer': question_refs[row['id']]['reference_answer'],
                    'evidenceCount': len(row['evidence']), 'review': notes[row['id']]['verdict'],
                    'reviewNote': notes[row['id']]['note'],
                    'runIds': ','.join(row['runIds'])})
csv_out('question-review.csv', reviews)

stats = {}
for kind, rows in groups.items():
    d = sorted(r['durationMs'] for r in rows)
    stats[kind] = {'total': len(rows), 'statuses': dict(Counter(r['status'] for r in rows)),
                   'errors': dict(Counter(r['errorCode'] for r in rows if r.get('errorCode'))),
                   'avgSeconds': round(sum(d) / len(d) / 1000, 2),
                   'p50Seconds': d[math.ceil(len(d) * .5) - 1] / 1000,
                   'p95Seconds': d[math.ceil(len(d) * .95) - 1] / 1000,
                   'totalTokens': sum(r['usage']['totalTokens'] for r in rows),
                   'withEvidence': sum(bool(r['evidence']) for r in rows),
                   'answersWithoutEvidence': sum(bool(r.get('answer')) and not r['evidence'] for r in rows)}
stats['applicationFields'] = metrics
dump('metrics.json', stats)

combined = []
for kind, rows in groups.items():
    for row in rows:
        combined.append({'类别': '申请' if kind == 'applications' else '问询', '编号': row['id'],
                         '终态': row['status'], '错误码': row.get('errorCode') or '',
                         '耗时秒': round(row['durationMs']/1000, 2), 'Token': row['usage']['totalTokens'],
                         '证据数': len(row['evidence']), 'runId': ','.join(row['runIds'])})
csv_out('逐题运行结果.csv', combined)
record = {'generatedAt': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
          'gitHead': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
          'model': 'deepseek-v4.1-flash', 'apiModelId': 'deepseek-flash',
          'execution': '两个进程分别串行运行10题；非独立串行性能基准；fresh；泄漏检查开启',
          'hashes': {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in [*sorted((ROOT/'inputs').glob('*.jsonl')), DATA/'loan_application.csv', DATA/'question_public.csv', DATA/'公开测试集答案.csv']}}
dump('batch-record.json', record)

start = json.loads((ROOT/'start-record.json').read_text())
changed = [p for p,h in start['codeHashes'].items()
           if hashlib.sha256((REPO/'ocft-backend'/p).read_bytes()).hexdigest() != h]
record['changedCodeDuringRecordedInterval'] = changed
record['runtime'] = start['runtime']
dump('batch-record.json', record)

all_runs = []
for kind, rows in groups.items():
    for row in rows:
        all_runs.append({'kind':'申请' if kind=='applications' else '问询','id':row['id'],
                         'status':row['status'],'seconds':round(row['durationMs']/1000,2),
                         'tokens':row['usage']['totalTokens'],'evidence':len(row['evidence']),
                         'error':row.get('errorCode') or '', 'runId':','.join(row['runIds'])})
apps = []
application_notes = json.loads((ROOT/'application-notes.json').read_text())
for row in comparison:
    apps.append({'id':row['applicationId'],'status':row['status'],'risk':row.get('systemRisk'),
                 'referenceRisk':row['referenceRisk'],'riskExact':row['candidateRiskExact'],
                 'amount':row.get('systemCredit'),'referenceAmount':row['referenceCredit'],
                 'exact':('一致' if row['eligibleExact'] else '不一致') if row['referenceNumeric'] else '非数值参考',
                 'within':('是' if row['eligibleWithin'] else '否') if row['referenceNumeric'] else '不适用',
                 'note':application_notes.get(row['applicationId'], '')})
qs = [{'id':r['questionId'],'status':r['status'],'question':r['question'],
       'verdict':r['review'],'note':r['reviewNote']} for r in reviews]
field_summary = (f"申请评级严格一致{metrics['candidateRiskExactCount']}/10；数值额度区间精确一致"
                 f"{metrics['eligibleExactCount']}/{metrics['numericReferenceCount']}；非数值参考"
                 f"{metrics['referenceNonNumericCount']}笔单列复核。")
dump('workbook-data.json', {'metrics':stats,'runs':all_runs,'applications':apps,
                          'questions':qs,'fieldSummary':field_summary})

state_name = {'succeeded':'成功','needs_confirmation':'待确认','failed':'失败','runner_error':'执行异常'}
summary_lines = []
for kind,label in [('applications','申请'),('questions','问询')]:
    m=stats[kind]; s=m['statuses']
    summary_lines.append(f"|{label}|{m['total']}|{s.get('succeeded',0)}|{s.get('needs_confirmation',0)}|{s.get('failed',0)+s.get('runner_error',0)}|{m['avgSeconds']}|{m['p95Seconds']:.2f}|{m['totalTokens']:,}|{m['withEvidence']}|")
app_lines = [f"|{r['id']}|{state_name.get(r['status'],r['status'])}|{r['risk'] or '未提取'}|{r['referenceRisk']}|{'是' if r['riskExact'] else '否'}|{r['amount'] if r['amount'] is not None else '未提取'}|{r['referenceAmount']}|{r['exact']}|" for r in apps]
q_lines = [f"|{r['id']}|{state_name.get(r['status'],r['status'])}|{r['verdict']}|{r['note']}|" for r in qs]
report = f'''# 赛题04公开数据评测结果

评测日期：2026-10-24。Git：`{start['gitHead']}`。本轮输入为主办方公开10笔申请、10道问询；由原始业务列白名单重新准备，20题均 fresh 调用统一 `eval.run → run_service.create_run`，未关闭泄漏检查。此次没有修改运行时规则、模型、工具、提示词或参考答案。

## 汇总

|类别|题数|成功|待确认|失败|平均秒|P95秒|Token|有证据题数|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(summary_lines)}

{field_summary} 这些是单字段比对，不能当作整份尽调报告的正确率。`needs_confirmation` 表示等待业务确认，本次未自动确认。

## 10笔申请

评级严格按参考原文比较，因此“低风险”与“低-中风险”不算严格一致。额度单位为万元；数值“精确一致”要求两个区间端点相同，另外保留区间重叠和包含指标。拒贷/极小额度不人为补数值阈值。

|编号|终态|系统评级|参考评级|严格一致|系统额度|参考额度|额度区间精确一致|
|---|---|---|---|---|---|---|---|
{chr(10).join(app_lines)}

字段从本次持久化的 `build_dd_report` / `calc_credit_limit` 证据提取，未重算业务结果补缺；待确认字段仍是候选分析，不能冒充已确认结果。最终文本与证据额度是否一致见 `application-comparison.csv` 的 `finalTextCreditMatch`；未检出不直接判一致。

### 字段符合之外仍存在的问题

- LA003 报告摘要写“需业务人员确认”，风险段又写“无需人工复核”，前后表述冲突。其经营现金流为3200→3800→1200万元，却写“逐年下降”，趋势描述错误。当前终态待确认未被自动确认。
- LA010 报告摘要写“需业务人员确认”，但运行终态是 `succeeded`。角色提示、文本和终态是否使用同一确认门禁需核对，不能因评级与额度符合就视为整份报告无缺陷。
- LA003 / LA008 / LA009 自动额度解析未检出；人工已在最终报告中核对0 / 1000–1200 / 2000–2500万元，与证据一致。解析器未检出不代表答案缺失，不修改旧评分器来制造自动通过。
- 两笔非数值参考LA003、LA006均为高风险、额度0，拒贷方向相符；仍保留非数值与待确认标记，不混入8笔数值区间精确率。

## 10道问询

以下为逐题人工复核的参考要点覆盖，未定义自动全文评分，也不声称官方比赛得分。复核标记区分核心符合、细项遗漏、参考与明细口径冲突；原答复、参考、runId均保留在 `question-review.csv`。

|编号|终态|复核结论|差异与依据|
|---|---|---|---|
{chr(10).join(q_lines)}

## 与上一份10笔申请归档比较

上一份完整申请归档为 `dd04-multi-agent-skills`（代码 `{baseline_summary['codeSha'][:7]}`）。本次未复用旧运行，只在离线比对阶段用同一标准重新统计旧表：

|指标|上一轮|本轮|
|---|---:|---:|
|成功 / 待确认|{baseline_summary['statuses'].get('succeeded',0)} / {baseline_summary['statuses'].get('needs_confirmation',0)}|{stats['applications']['statuses'].get('succeeded',0)} / {stats['applications']['statuses'].get('needs_confirmation',0)}|
|评级严格一致|{baseline_metrics['candidateRiskExactCount']}/10|{metrics['candidateRiskExactCount']}/10|
|数值额度区间精确一致|{baseline_metrics['eligibleExactCount']}/{baseline_metrics['numericReferenceCount']}|{metrics['eligibleExactCount']}/{metrics['numericReferenceCount']}|

旧报告的额度7/10混合了数值区间与拒贷语义，不能直接与本表数值8笔口径比较。版本及运行时配置不同，差异不归因于某个单独改动；没有宣称20题的全文正确率提升。

## 执行与证据

- 身份模型：`{start['runtime']['model']}`；现有接口模型ID：`{start['runtime']['apiModelId']}`，本次未独立核验供应商别名映射。
- 两个进程各自串行跑10题，角色内部沿用现有并行；耗时包含失败，不是独立串行性能基准。P50/P95为 nearest-rank。
- 运行时路径不读取参考答案。离线评分脚本在20题完成、无标签结果及证据落盘后读取参考列；问询参考仅在评测侧逐题阅读，未输入模型。
- 公开输入和参考文件SHA256、运行配置、代码哈希见 `start-record.json` / `batch-record.json`。记录期间代码哈希变化：{changed or '无'}。
- 归档中的企业名、人员名、地址与号码重新代号化；原运行仍可用runId在数据库追溯。不导出.env、主密钥和连接串。
- 本轮没有业务源码变更，未重复跑单元测试、前端lint/build；结论来自本轮20题真实模型运行，未测试非公开集，也未制作正式提交文件。

## 文件

- [Excel结果表](outputs/dd04-public-latest/公开评测结果.xlsx)
- [20题运行表](逐题运行结果.csv)
- [申请字段比对](application-comparison.csv)
- [问询原答复、参考及复核](question-review.csv)
- [完整脱敏证据](run-evidence.json)
- [机器可读指标](metrics.json)
- [申请执行日志](applications-execution.log) / [问询执行日志](questions-execution.log)
'''
(ROOT/'公开评测报告.md').write_text(report, encoding='utf-8')
print(json.dumps(stats, ensure_ascii=False, indent=2))
