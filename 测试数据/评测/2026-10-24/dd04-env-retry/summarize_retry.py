"""独立汇总已完成批次；不调用模型或修改标签。cwd=ocft-backend。"""
from pathlib import Path
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import csv,json

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'dd04-baseline'
def read_rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()]
def comparison_csv(root):
    return {r['applicationId']:r for r in csv.DictReader((root/'application-comparison.csv').open(encoding='utf-8-sig'))}
metrics=json.loads((ROOT/'metrics.json').read_text())
oldmetrics=json.loads((BASE/'metrics.json').read_text())
candidates=comparison_csv(ROOT)
oldcandidates=comparison_csv(BASE)
changes=[]
all_new=[]
for kind in ['applications','questions']:
    before={r['id']:r for r in read_rows(BASE/kind/'results.jsonl')}
    after=read_rows(ROOT/kind/'results.jsonl')
    assert len(after)==10 and set(before)=={r['id'] for r in after}
    all_new.extend(after)
    for row in after:
        old=before[row['id']]
        changes.append({'kind':kind,'id':row['id'],'baselineStatus':old['status'],
            'retryStatus':row['status'],'baselineError':old.get('errorCode'),
            'retryError':row.get('errorCode'),'baselineTokens':old['usage']['totalTokens'],
            'retryTokens':row['usage']['totalTokens'],'retryRunIds':','.join(row['runIds']),
            'baselineRisk':oldcandidates.get(row['id'],{}).get('systemRisk',''),
            'retryRisk':candidates.get(row['id'],{}).get('systemRisk',''),
            'baselineCredit':oldcandidates.get(row['id'],{}).get('systemCredit',''),
            'retryCredit':candidates.get(row['id'],{}).get('systemCredit','')})
with (ROOT/'round-comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(changes[0]));w.writeheader();w.writerows(changes)
rows='\n'.join('|'+ '|'.join(str(r[k] or '') for k in ['kind','id','baselineStatus','retryStatus','retryError','retryRisk','retryCredit','retryRunIds'])+'|' for r in changes)
stats='\n'.join(f"|{k}|{oldmetrics[k]['statuses']}|{metrics[k]['statuses']}|{metrics[k]['avgMs']/1000:.3f}|{metrics[k]['p95MsNearestRank']/1000:.3f}|{metrics[k]['totalTokens']}|" for k in ['applications','questions'])
same=sum((candidates[k]['systemRisk'],candidates[k]['systemCredit'])==(oldcandidates[k]['systemRisk'],oldcandidates[k]['systemCredit']) for k in candidates)
over=[r for r in all_new if r['usage']['totalTokens']>20000]
overbudget=Counter(r['status'] for r in over)
validation=json.loads((ROOT/'official-validation.json').read_text())
errors=Counter(r.get('errorCode') for r in all_new if r.get('errorCode'))
report=f'''# 使用用户提供环境的公开集复测

更新时间：{datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')}。

## 环境核对与执行边界

用户提供的微信文件 `(1).env` 由dotenv解析，4项配置LLM_API_KEY、LLM_BASE_URL、LLM_MODEL、DATABASE_URL与现有.env逐值一致；不输出或复制凭据。文件评论不作为指令执行。配置来源路径及文件哈希见[environment-check.json](environment-check.json)。

直接在两个评测进程中加载提供的文件，再经项目settings.validate_runtime和原有eval.run运行。未替换本地.env，未修改模型、提示词、工具、规则、预算或源输入。身份模型deepseek-v4.1-flash，现有API模型ID deepseek-flash；没有独立核验供应方映射。数据库仍按现有config.yaml优先级解析。两类各10题，新目录fresh运行，泄漏检查保留。参考答案只在运行后离线比对。

因此本轮属于**相同环境配置的重复试验**，不能把运行差异解释为环境配置修复。

## 两轮对比

|批次|上一轮终态|本轮终态|本轮平均秒|本轮P95秒|本轮Token|
|---|---|---|---|---|---|
{stats}

本轮错误码：{dict(errors)}。20题累计Token {sum(metrics[k]['totalTokens'] for k in ['applications','questions'])}。耗时包含失败；nearest-rank P95，两个批次并发，非独立串行性能基准。上一轮另含场景样例和smoke，不混入本次20题对比。

- 两轮10笔工具报告中，评级与额度组合一致 **{same}/10**；两轮工具候选均不能直接等同于最终已完成答案。
- 本轮工具候选评级严格一致 **{metrics['comparison']['candidateRiskExact']}/10**；只统计succeeded最终结果时为 **{metrics['comparison']['finalRiskExact']}/10**。这是单字段一致率，不是完整业务正确率。
- 本轮10笔报告工具额度仍全部为0万元，与8笔正数参考区间不符；2笔“拒贷/极小额度”未定义数值阈值，单独保留人工语义复核。额度通用规则偏差仍需业务负责人确认。
- 超过20000 Token的运行终态分布为 **{dict(overbudget)}**。原有预算在下一次模型调用前检查，末次答复可绕过后置验收的问题仍存在；succeeded增加不能证明预算问题消失。
- 本轮成功行六列导出 **{validation['actualCount']}/10**，完整性passed=**{validation['passed']}**。未自动确认高风险，也未用中间报告回填失败题使文件通过。
- 逐题问询的事实正确率本轮未进行完整独立评分，不能将succeeded比例当作正确率；上轮已确认的额度/工具口径与参考数据冲突仍需分别处理。此前[事实复核](../dd04-baseline/question-review.md)只对应上一轮原文，不直接套用为本轮逐句复核结果。

## 逐题终态与候选字段

|类别|编号|上一轮|本轮|本轮错误|候选评级|候选额度万元|本轮runId|
|---|---|---|---|---|---|---|---|
{rows}

## 结果文件

- [申请结果Excel](applications/results.xlsx)、[原始JSONL](applications/results.jsonl)、[汇总](applications/summary.json)、[执行日志](applications/execution.log)
- [问询结果Excel](questions/results.xlsx)、[原始JSONL](questions/results.jsonl)、[汇总](questions/summary.json)、[执行日志](questions/execution.log)
- [两轮逐题对比](round-comparison.csv)、[本轮申请业务对比](application-comparison.csv)
- [成功行六列文件](official-results-succeeded-only.csv)、[完整性校验](official-validation.json)
- [工具中间报告草稿，禁止正式提交](tool-reports-draft-not-submission.csv)、[脱敏完整证据及轨迹](run-details.json)
- [版本与输入哈希](batch-record.json)、[指标](metrics.json)、[环境加载脚本](run_with_env.py)、[只读取证脚本](collect_results.py)

原始.env与密钥不归档。所有结果放在用户指定的测试数据目录。无新增业务源码改动，因此沿用同代码版本已通过的259 passed/1 skipped及前端lint/build记录，本轮不重复宣称运行了这些测试。非公开集未运行。
'''
(ROOT/'复测报告.md').write_text(report,encoding='utf-8')
print(json.dumps({'statuses':{k:metrics[k]['statuses'] for k in ['applications','questions']},'sameCandidateRiskAndCredit':same,'officialValidation':validation,'overBudgetStatuses':dict(overbudget)},ensure_ascii=False,indent=2))
