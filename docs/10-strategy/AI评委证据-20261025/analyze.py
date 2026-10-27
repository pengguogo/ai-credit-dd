"""只读复核本次真实运行，参考只用于离线字段比对。"""
import os,sys,json,csv,hashlib,math,statistics
from pathlib import Path
from collections import Counter
root=Path(__file__).resolve().parents[3]; here=Path(__file__).parent; backend=root/'ocft-backend'
sys.path.insert(0,str(backend));m=json.loads((here/'live/manifest.json').read_text())
os.environ['OCFT_DB_CONFIG']=str(Path(m['databasePath']).parent/'no-config.yaml')
os.environ['DATABASE_URL']='sqlite:///'+m['databasePath']
from eval.dd04_credit import collect_runs,compare_amounts
from eval.dd04 import validate_results
from app.db import SessionLocal
from app.models import LlmCall
ref=list(csv.DictReader((root/'docs/00-rules/赛题/赛题04_企业智能信贷尽调/data/公开测试集答案.csv').open(encoding='utf-8-sig')))
rows,fields=compare_amounts(collect_runs(here/'live/applications/results.jsonl'),ref)
(here/'field-comparison.json').write_text(json.dumps({'summary':fields,'rows':rows},ensure_ascii=False,indent=2,default=str))
result={'baseCommit':m['baseCommit'],'runtimeHashChanges':m.get('runtimeHashChanges'),'fields':fields,'format':validate_results(root/'docs/00-rules/赛题/赛题04_企业智能信贷尽调/data/loan_application.csv',here/'live/official-results.csv')}
for kind in ('applications','questions'):
 r=[json.loads(l) for l in (here/'live'/kind/'results.jsonl').read_text().splitlines()]
 ds=sorted(v['durationMs']/1000 for v in r)
 result[kind]={'count':len(r),'statuses':dict(Counter(v['status'] for v in r)),'meanSeconds':statistics.mean(ds),'p50Seconds':statistics.median(ds),'p95NearestRankSeconds':ds[math.ceil(.95*len(ds))-1],'totalTokens':sum(v['usage']['totalTokens'] for v in r),'evidenceCounts':{v['id']:len(v['evidence']) for v in r}}
with SessionLocal() as db:result['auditedModels']=list(dict.fromkeys(v[0] for v in db.query(LlmCall.model).all()))
rp=here/'repeat/live/applications/results.jsonl'
if rp.exists():
 first=json.loads((here/'live/applications/results.jsonl').read_text().splitlines()[0]);second=json.loads(rp.read_text().splitlines()[0])
 result['repeatLA001']={'firstRunIds':first['runIds'],'secondRunIds':second['runIds'],'statusSame':first['status']==second['status'],'textIdentical':first['answer']==second['answer'],'firstTextSha256':hashlib.sha256(first['answer'].encode()).hexdigest(),'secondTextSha256':hashlib.sha256(second['answer'].encode()).hexdigest(),'scope':'单一申请两次；字段与版式另行核验，不能外推十笔重复稳定性'}
if 'repeatLA001' in result:
 original=json.loads((here/'live/applications/evidence.json').read_text())['LA001']
 repeated=json.loads((here/'repeat/live/applications/evidence.json').read_text())['LA001']
 def credit_fields(evs):
  found=[e['snapshot'] for e in evs if e.get('source',{}).get('calc') in ('build_dd_report','calc_credit_limit')]
  return {k:found[-1].get(k) for k in ('riskLevel','suggestedCreditAmount')} if found else None
 result['repeatLA001']['firstFields']=credit_fields(original)
 result['repeatLA001']['secondFields']=credit_fields(repeated)
 result['repeatLA001']['fieldsSame']=credit_fields(original)==credit_fields(repeated)
 result['repeatLA001']['fiveSectionsBothPresent']=all(all('## '+h in a for h in ('企业概况','财务分析','风险提示','额度建议','风控条件')) for a in (first['answer'],second['answer']))

# 版本与打包取件路径的静态复核，不执行封包
import yaml
man=yaml.safe_load((root/'submission/dd04/manifest.generated.yaml').read_text())
result['delivery']={'manifestCommit':man['code']['commit_sha'],'primaryPhonePresent':man['contact']['primary_phone'] not in ('TBD',None,''),'primaryEmailPresent':man['contact']['primary_email'] not in ('TBD',None,''),'mp4Files':[str(p.relative_to(root)) for p in (root/'submission').rglob('*.mp4')],'scriptPitchPathExists':(root/'docs/60-pitch/演示脚本.md').exists(),'actualPitchPathExists':(root/'docs/60-pitch/赛题04演示脚本.md').exists(),'screenshotSourceExists':[(root/'submission/dd04/artifacts'/f).exists() for f in ('截图01_尽调报告_完整.png','截图02_财务分析.png','截图03_风险提示与反欺诈.png','截图04_自然语言问询.png')]}
private=root/'系统输出/智算先锋队_赛题04_非公开测评集结果.csv';rehearsal=root/'系统输出/非公开测评集结果-演练衍生.csv'
result['delivery']['privateEqualsRehearsal']=private.read_bytes()==rehearsal.read_bytes()
(here/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
