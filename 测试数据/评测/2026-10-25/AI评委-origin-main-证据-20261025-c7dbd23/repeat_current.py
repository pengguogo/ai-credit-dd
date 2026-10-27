import os,sys,tempfile,json,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
backend=Path.cwd(); root=backend.parent
out=Path('/Users/dawn/ai马拉松/测试数据/评测/2026-10-25/AI评委-origin-main-证据-20261025-c7dbd23')
job=out/'repeat';job.mkdir(exist_ok=False)
local=Path(tempfile.mkdtemp(prefix='ocft-dd04-acceptance-'))
os.environ['OCFT_DB_CONFIG']=str(local/'no-config.yaml')
os.environ['DATABASE_URL']='sqlite:///'+str(local/'acceptance.db')
sys.path.insert(0,str(backend))
from eval.dd04 import prepare_inputs,export_results
from eval.run import evaluate
from app.db import init_db,seed_business_data,SessionLocal
from app.models import LoanApplication
from app.config import settings
source=root/'docs/00-rules/赛题/赛题04_企业智能信贷尽调/data'
for name,kind in []:
 inputs=prepare_inputs(source/name,kind,'enterprise_dd')
 path=out/'inputs'/f'{kind}.jsonl';path.parent.mkdir(exist_ok=True)
 path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in inputs))
def hashes():
 paths=list((backend/'app').rglob('*.py'))
 paths += [p for p in (backend/'app/compliance/lexicon').glob('*') if p.is_file()]
 paths += [p for p in (backend/'scenarios').rglob('*') if p.is_file() and p.suffix in {'.yaml','.yml','.md','.csv','.json'}]
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
def stamp():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

import csv,threading
from app import llm
fields={'enterprise_name','credit_code','legal_person','legal_person_id','register_address','actual_controller','shareholder_name','related_enterprise_name','guaranteed_party'}
sensitive=[]
for p in (backend/'scenarios/dd04/data').glob('*.csv'):
 for row in csv.DictReader(p.open(encoding='utf-8-sig')):
  sensitive.extend((k,v) for k,v in row.items() if k in fields and v and len(v.strip())>=2)
original=llm.complete_with_tools
audits=[]
def audited(messages,*a,**kw):
 text=json.dumps(messages,ensure_ascii=False)
 hits=sorted(set(k for k,v in sensitive if v in text))
 result=original(messages,*a,**kw)
 audits.append({'index':len(audits)+1,'unmaskedFieldTypes':hits,'messageCount':len(messages),'responseModel':result.get('model')})
 return result
llm.complete_with_tools=audited

record={'startedAt':stamp(),'baseCommit':'c7dbd231b955cb7a2dfcf317212773b8cd65eae4',
 'scope':'c7dbd23 origin/main 逐条评委复验；官方10申请+10问询；独立SQLite；参考仅离线对照',
 'model':settings.llm_model,'runtimeHashes':hashes(),
 'inputHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'inputs').glob('*.jsonl')},
 'businessHashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (backend/'scenarios/dd04/data').glob('*.csv')},
 'databasePath':str(local/'acceptance.db'),'referenceReadByRuntime':False}
init_db();seed_business_data()
with SessionLocal() as db:
 record['applicationIds']=[r.application_id for r in db.query(LoanApplication).order_by(LoanApplication.application_id)]
 assert len(record['applicationIds'])==10 and 'LA011' not in record['applicationIds']
(job/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print('FROZEN',len(record['runtimeHashes']),'files',record['applicationIds'],flush=True)
for kind in ('applications',):
 evaluate(out/'inputs'/f'{kind}.jsonl',job/kind,fresh=True,limit=1)
record['endedAt']=stamp();after=hashes();record['runtimeHashChanges']=[p for p in sorted(record['runtimeHashes'].keys()|after.keys()) if record['runtimeHashes'].get(p)!=after.get(p)]
(job/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print('RUNTIME_HASH_CHANGES',record['runtimeHashChanges'],flush=True)

from eval.dd04_review import collect_evidence
rows=[json.loads(l) for l in (job/'applications/results.jsonl').read_text().splitlines()]
(job/'applications/evidence.json').write_text(json.dumps(collect_evidence(rows),ensure_ascii=False,indent=2,default=str))
(job/'outbound-audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2))
print('REPEAT COMPLETE', flush=True)
