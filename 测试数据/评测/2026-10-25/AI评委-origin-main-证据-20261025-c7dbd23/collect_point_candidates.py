"""生成52项官方参考要点的候选原文；匹配只是检索，不自动判业务正确。"""
from pathlib import Path
import json,csv,re
here=Path(__file__).parent
source=Path('/tmp/ocft-origin-main-judge-20261025-c7dbd23/docs/00-rules/赛题/赛题04_企业智能信贷尽调/data/公开测试集答案.csv')
rows={r['id']:r for r in map(json.loads,(here/'live/applications/results.jsonl').read_text().splitlines())}
patterns={'风险评级':'尽调结论','额度':'建议.*额度|建议.*万元','财务指标':'资产负债率|净利率','现金流质量':'经营现金流.*净利润|经营现金流/净利润','结论完整':'尽调结论','结论明确':'尽调结论','结论有依据':'尽调结论','营收增长':'营收.*增长|营收.*同比','应收账款占比':'应收账款/营业收入|应收账款占','舆情':'舆情.*原始|舆情.*评分','资产负债率':'资产负债率','逾期与逾期担保':'逾期.*担保|逾期.*次','法人限高':'限高','拒贷':'额度.*0|一票否决','周转率':'周转次数|周转天数','净利率':'净利率','负债率':'资产负债率','营收波动':'营收.*同比|营收.*下降|营收.*波动','现金流为正':'经营现金流.*[1-9]|经营现金流（万元）','应收账款过高':'应收账款.*过高|应收账款/营业收入','现金流与利润背离':'现金流.*背离|现金流.*利润','涉诉':'全部涉诉|涉诉.*万元','负债率健康':'资产负债率','资产质量':'应收账款.*|资产质量','担保方式':'担保.*抵押|担保.*保证','利率':'利率方向','营收现金流背离':'F01|营收.*现金流','其他应收款异常':'其他应收.*异常|F04|其他应收.*偏高','担保圈':'担保圈','核查':'核查|核实'}
items=[]
for ref in csv.DictReader(source.open(encoding='utf-8-sig')):
 r=rows[ref['application_id']];answer=r.get('answer') or '';lines=answer.splitlines()
 for point in ref['scoring_points'].split(';'):
  pattern=next((v for k,v in patterns.items() if k in point),re.escape(point))
  matches=[l for l in lines if len(l.strip())>=12 and re.search(pattern,l)]
  items.append({'applicationId':r['id'],'runIds':r['runIds'],'officialPoint':point,'candidateQuotes':matches[:3],'retrievalStatus':'有候选摘录，未自动判分' if matches else '需全文检查','businessConfirmed':False})
(here/'scoring-point-candidates.json').write_text(json.dumps(items,ensure_ascii=False,indent=2))
text=['# 官方52项参考要点候选摘录','', '> 以下只是从本轮真实回答中检索出的原文，未自动判分，不是52项全通过或业务签核。每项绑定本轮runId；完整正文与同run证据另存。','', '| 申请 | 官方要点 | 本轮runId | 候选原文 |', '|---|---|---|---|']
for i in items:
 q='；'.join(i['candidateQuotes'][:2]).replace('|','／').replace('\n',' ') or '未检索到，需全文核验'
 text.append(f"| {i['applicationId']} | {i['officialPoint']} | {','.join(i['runIds'])} | {q} |")
(here/'scoring-point-candidates.md').write_text('\n'.join(text)+'\n')
print('points',len(items),'withCandidate',sum(bool(i['candidateQuotes']) for i in items))
