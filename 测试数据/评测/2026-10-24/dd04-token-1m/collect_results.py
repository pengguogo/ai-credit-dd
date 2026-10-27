"""本轮评测只读取证：不调用模型、不修改运行记录，参考答案仅在此离线比对。"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'ocft-backend'))
from app.db import SessionLocal
from app.models import Evidence
from app.services.run_service import get_run, masked_snapshot

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parents[3] / 'docs/00-rules/赛题/赛题04_企业智能信贷尽调/data'
FIELDS = ['application_id', 'enterprise_id', 'risk_level', 'suggested_credit_amount',
          'due_diligence_conclusion', 'scoring_points']

def read_results(kind):
    return [json.loads(line) for line in (ROOT / kind / 'results.jsonl').read_text().splitlines()]

def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def interval(text):
    if not re.fullmatch(r'\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?', str(text)):
        return None
    nums = [float(n) for n in str(text).split('-')]
    return nums[0], nums[-1]

all_rows = {kind: read_results(kind) for kind in ['applications', 'questions']}
details = {}
with SessionLocal() as db:
    for kind, rows in all_rows.items():
        for row in rows:
            for run_id in row['runIds']:
                run, traces, evidence_ids = get_run(db, run_id, 'eval_runner')
                evidence = db.query(Evidence).filter(Evidence.id.in_(evidence_ids)).all()
                details[run_id] = {
                    'status': run.status, 'answer': run.answer, 'errorCode': run.error_code,
                    'startedAtUtc': run.started_at.isoformat() + 'Z',
                    'finishedAtUtc': run.finished_at.isoformat() + 'Z' if run.finished_at else None,
                    'traces': [{'tool': t.tool_name, 'args': t.args, 'status': t.status,
                                'errorCode': t.error_code, 'evidenceRef': t.result_ref} for t in traces],
                    'evidence': [{'id': e.id, 'source': e.source_ref,
                                  'snapshot': masked_snapshot(e)} for e in evidence],
                }
(ROOT / 'run-details.json').write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding='utf-8')

refs = {r['application_id']: r for r in csv.DictReader((DATA / '公开测试集答案.csv').open(encoding='utf-8-sig'))}
comparisons, drafts, final = [], [], []
for row in all_rows['applications']:
    reports = [e['snapshot'] for rid in row['runIds'] for e in details[rid]['evidence']
               if e['source'].get('calc') == 'build_dd_report']
    report = reports[-1] if reports else {}
    ref = refs[row['id']]
    candidate = {
        'application_id': row['id'], 'enterprise_id': report.get('enterpriseId', ''),
        'risk_level': report.get('riskLevel', ''),
        'suggested_credit_amount': report.get('suggestedCreditAmount', ''),
        'due_diligence_conclusion': report.get('dueDiligenceConclusion', ''),
        'scoring_points': ';'.join(report.get('scoringPoints') or []),
    }
    eligible = row['status'] == 'succeeded' and bool(report)
    if report:
        drafts.append(candidate)
    if eligible:
        final.append(candidate)
    actual, expected = interval(candidate['suggested_credit_amount']), interval(ref['suggested_credit_amount'])
    match = '' if not (actual and expected) else expected[0] <= actual[0] <= actual[1] <= expected[1]
    comparisons.append({
        'applicationId': row['id'], 'status': row['status'], 'errorCode': row.get('errorCode'),
        'runIds': ','.join(row['runIds']), 'reportEvidencePresent': bool(report), 'finalEligible': eligible,
        'systemRisk': candidate['risk_level'], 'referenceRisk': ref['risk_level'],
        'candidateRiskExact': candidate['risk_level'] == ref['risk_level'],
        'finalRiskExact': eligible and candidate['risk_level'] == ref['risk_level'],
        'systemCredit': candidate['suggested_credit_amount'], 'referenceCredit': ref['suggested_credit_amount'],
        'creditNumericRangeWithin': match,
        'creditReview': '语义需复核：拒贷/极小额度未定义数值阈值' if expected is None else '',
    })
write_csv(ROOT / 'application-comparison.csv', comparisons, list(comparisons[0]))
write_csv(ROOT / 'official-results-succeeded-only.csv', final, FIELDS)
write_csv(ROOT / 'tool-reports-draft-not-submission.csv', drafts, FIELDS)

stats = {}
for kind, rows in all_rows.items():
    durations = sorted(r['durationMs'] for r in rows)
    statuses = {s: sum(r['status'] == s for r in rows) for s in sorted({r['status'] for r in rows})}
    stats[kind] = {'total': len(rows), 'statuses': statuses,
        'p50MsNearestRank': durations[(len(rows)+1)//2-1],
        'p95MsNearestRank': durations[(95*len(rows)+99)//100-1],
        'maxMs': max(durations), 'over30s': sum(d > 30000 for d in durations),
        'totalTokens': sum(r['usage']['totalTokens'] for r in rows),
        'avgMs': round(sum(durations)/len(rows)),
        'answersWithoutEvidence': sum(bool(r.get('answer')) and not r.get('evidence') for r in rows)}
stats['comparison'] = {'denominator': len(refs), 'finalRiskExact': sum(c['finalRiskExact'] for c in comparisons),
                       'candidateRiskExact': sum(c['candidateRiskExact'] for c in comparisons),
                       'officialRows': len(final), 'draftRows': len(drafts)}
(ROOT / 'metrics.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(stats, ensure_ascii=False, indent=2))
