from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import csv,json
ROOT=Path(__file__).resolve().parent
rounds=[('原始基线','dd04-baseline'),('同环境复测','dd04-env-retry'),('1M累计预算','dd04-token-1m')]
summary=[]
for name,folder in rounds:
    m=json.loads((ROOT.parent/folder/'metrics.json').read_text())
    for kind in ['applications','questions']:
        summary.append(f"|{name}|{kind}|{m[kind]['statuses']}|{m[kind]['avgMs']/1000:.3f}|{m[kind]['p95MsNearestRank']/1000:.3f}|{m[kind]['totalTokens']}|")
rows=[]
for kind in ['applications','questions']:
    before={r['id']:r for r in map(json.loads,(ROOT.parent/'dd04-env-retry'/kind/'results.jsonl').read_text().splitlines())}
    after=list(map(json.loads,(ROOT/kind/'results.jsonl').read_text().splitlines()))
    assert len(after)==10 and set(before)=={r['id'] for r in after}
    for row in after:
        old=before[row['id']]
        rows.append({'kind':kind,'id':row['id'],'oldStatus':old['status'],'newStatus':row['status'],
            'oldError':old.get('errorCode'),'newError':row.get('errorCode'),
            'newTokens':row['usage']['totalTokens'],'newRunIds':','.join(row['runIds'])})
with (ROOT/'budget-comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
metrics=json.loads((ROOT/'metrics.json').read_text())
validation=json.loads((ROOT/'official-validation.json').read_text())
candidate=list(csv.DictReader((ROOT/'application-comparison.csv').open(encoding='utf-8-sig')))
zero=sum(r['systemCredit']=='0' for r in candidate)
errors=Counter(r['newError'] for r in rows if r['newError'])
report=f'''# RUN_MAX_TOTAL_TOKENS=1048576 公开集复测

记录时间：{datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')}。代码基线cfa4d33，场景enterprise_dd。

## 已完成的配置修改

仅在后端本地.env新增 `RUN_MAX_TOTAL_TOKENS=1048576`，运行时settings加载断言通过，后端重启后健康检查HTTP200，前端HTTP200。用户微信提供的环境文件仍用于加载原有四项连接配置，原件未修改；提供的四项值均与本地原有配置相同，凭据未回显或归档。

值的依据：[DeepSeek API官方文档](https://api-docs.deepseek.com/quick_start/pricing/)公布deepseek-flash为V4.1-Flash-1017、上下文1M；[官方模型config.json](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017/blob/main/config.json)的max_position_embeddings=1048576。**该数值是单次上下文窗口；多次调用累计用量没有对应的模型硬上限，本项目按此规模设置应用预算。**

仍沿用模型deepseek-v4.1-flash、API ID deepseek-flash；单次输出上限2048、工具轮数6、run时限60秒。本轮没有修改这些参数或提示词、编排与业务公式。只有配置变化，已实际读取验证，没有新增业务源码或重跑上一轮的全量单测/lint/build。

## 三轮真实运行结果

|批次|题集|终态|平均秒|P95秒|总Token|
|---|---|---|---|---|---|
{chr(10).join(summary)}

每轮申请10笔、问询10个，fresh新目录；前两轮另有场景样例与smoke，不混入20题对比。两个题集进程并发，P95为nearest-rank，包含失败，不作串行生产性能声明。各轮保留完整原始结果，不覆盖，也不将不同时刻采用的预算混在一个批次。

本轮错误码：**{dict(errors)}**。详见[逐题预算前后对比](budget-comparison.csv)。超20000 Token后仍可继续执行已由本轮实际结果验证；如果还有round_limit_exceeded，它来自仍保留的6轮限制，不能归为Token上限或供应商API错误。没有因此自动放宽其他限制。

## 业务结果仍需修复

- 本轮{len(candidate)}笔申请中，工具报告额度为0的有 **{zero}笔**。额度参考为正区间的8笔仍需逐笔核对；拒贷/极小额度两笔保持语义待复核，不填默认结论。
- 工具候选评级严格一致 **{metrics['comparison']['candidateRiskExact']}/10**；仅succeeded最终结果评级严格一致 **{metrics['comparison']['finalRiskExact']}/10**。这都是单字段检查，不能替代完整业务正确率。
- succeeded-only六列导出{validation['actualCount']}/10，完整性校验passed=**{validation['passed']}**；待确认未自动确认，失败未用中间报告冒充成功。
- 自然语言问询本轮只汇总执行状态、证据和原答复，未重新完成全文事实/要点评分，不能把成功比例当正确率。
- 额度公式、评级差异、诉讼已执行完毕误归未结、事实推断及报告截断等问题，见[首轮缺陷证据](../dd04-baseline/公开评测报告.md)。该报告中的逐句问题绑定旧runId，本轮不得直接套用为逐句复核结论。

## 文件

- [申请Excel](applications/results.xlsx)、[原始JSONL](applications/results.jsonl)、[汇总](applications/summary.json)、[执行日志](applications/execution.log)
- [问询Excel](questions/results.xlsx)、[原始JSONL](questions/results.jsonl)、[汇总](questions/summary.json)、[执行日志](questions/execution.log)
- [申请评级与额度比对](application-comparison.csv)、[预算前后逐题状态](budget-comparison.csv)
- [成功行六列文件](official-results-succeeded-only.csv)、[完整性校验](official-validation.json)
- [工具中间报告草稿，不可作为正式提交](tool-reports-draft-not-submission.csv)、[脱敏完整证据](run-details.json)
- [批次配置与输入哈希](batch-record.json)、[指标](metrics.json)、[环境加载脚本](run_with_env.py)、[只读取证脚本](collect_results.py)

输入JSONL只保留id/question/scenarioId，泄漏检查未关闭；参考答案只在离线比对时读取。所有产物按用户要求位于测试数据目录。运行数据库未清空。非公开集未运行，完整正式提交未验收。
'''
(ROOT/'预算调整复测报告.md').write_text(report,encoding='utf-8')
print(json.dumps({'statuses':{k:metrics[k]['statuses'] for k in ['applications','questions']},'errors':dict(errors),'zeroCreditReports':zero,'validation':validation},ensure_ascii=False,indent=2))
