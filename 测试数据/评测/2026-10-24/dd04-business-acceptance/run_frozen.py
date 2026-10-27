import os,sys,tempfile,json,hashlib,subprocess
from pathlib import Path
from datetime import datetime,timezone
backend=Path.cwd(); root=backend.parent
out=root/'测试数据/评测/2026-10-24/dd04-business-acceptance'
job=out/'final';job.mkdir(exist_ok=True)
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
for name,kind in [('loan_application.csv','applications'),('question_public.csv','questions')]:
 inputs=prepare_inputs(source/name,kind,'enterprise_dd')
 path=out/'inputs'/f'{kind}.jsonl';path.parent.mkdir(exist_ok=True)
 path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in inputs))
def hashes():
 paths=list((backend/'app').rglob('*.py'))
 paths += [p for p in (backend/'app/compliance/lexicon').glob('*') if p.is_file()]
 paths += [p for p in (backend/'scenarios').rglob('*') if p.is_file() and p.suffix in {'.yaml','.yml','.md','.csv','.json'}]
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))}
def stamp():return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')
record={'startedAt':stamp(),'baseCommit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'scope':'含用户既有改动及本轮通用修复；官方业务CSV独立SQLite；真实模型统一入口；参考仅离线读取',
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
for kind in ('applications','questions'):
 evaluate(out/'inputs'/f'{kind}.jsonl',job/kind,fresh=True)
record['endedAt']=stamp();after=hashes();record['runtimeHashChanges']=[p for p in sorted(record['runtimeHashes'].keys()|after.keys()) if record['runtimeHashes'].get(p)!=after.get(p)]
(job/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print('RUNTIME_HASH_CHANGES',record['runtimeHashChanges'],flush=True)
print(json.dumps(export_results(source/'loan_application.csv',job/'applications/results.jsonl',job/'official-results.csv'),ensure_ascii=False),flush=True)
from eval.dd04_review import collect_evidence
for kind in ('applications','questions'):
 rows=[json.loads(l) for l in (job/kind/'results.jsonl').read_text().splitlines()]
 (job/kind/'evidence.json').write_text(json.dumps(collect_evidence(rows),ensure_ascii=False,indent=2,default=str))
print('COMPLETE; evidence archived',flush=True)
