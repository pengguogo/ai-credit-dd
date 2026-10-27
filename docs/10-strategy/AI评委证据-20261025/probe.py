"""评委故障注入探针：临时SQLite＋假模型，无真实模型费用，不改变业务源码。"""
import os,sys,tempfile,json
from pathlib import Path
root=Path(__file__).resolve().parents[3]; backend=root/'ocft-backend'
local=Path(tempfile.mkdtemp(prefix='judge-probe-'))
os.environ['OCFT_DB_CONFIG']=str(local/'absent.yaml')
os.environ['DATABASE_URL']='sqlite:///'+str(local/'probe.db')
os.environ['LLM_API_KEY']='fake-key'
os.environ['LLM_MODEL']=''
sys.path.insert(0,str(backend))
from app import llm
from app.main import app
from app.agent import dd_verify
from fastapi.testclient import TestClient
out={}
texts=iter(['该企业没有对外担保，也没有逾期，可以放款。','根据《虚构企业信贷尽调法》第999条，该企业必须获得贷款。'])
llm.complete_with_tools=lambda *a,**k: {'content':next(texts),'tool_calls':[],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},'model':'deepseek-v4.1-flash','finish_reason':'stop'}
with TestClient(app) as client:
 r=client.post('/api/agent/runs',json={'question':'请核查 E003 的对外担保和逾期，能否放款？','scenarioId':'enterprise_dd'},headers={'X-Actor-Id':'judge_probe'})
 data=r.json();out['no_evidence_business_claim']={'httpStatus':r.status_code,**{k:data.get(k) for k in ('runId','status','answer','errorCode','evidenceIds')}}
 conf=client.post('/api/agent/runs/'+data['runId']+'/confirmations',json={'answerVersion':1,'action':'confirm','idempotencyKey':'judge-probe-confirm'},headers={'X-Actor-Id':'unverified_business_officer'})
 out['unverified_confirmation']={'httpStatus':conf.status_code,'body':conf.json()}
 detail=client.get('/api/agent/runs/'+data['runId'],headers={'X-Actor-Id':'judge_probe'}).json()
 out['no_evidence_business_claim']['traceCount']=len(detail.get('toolTraces',[]))
 r2=client.post('/api/agent/runs',json={'question':'企业 E003 可以贷款吗？'},headers={'X-Actor-Id':'judge_probe'})
 d2=r2.json();out['fabricated_law']={'httpStatus':r2.status_code,**{k:d2.get(k) for k in ('status','answer','errorCode','evidenceIds')}}
source=[{'annual':[{'year':2021,'revenue':100},{'year':2022,'revenue':200},{'year':2023,'revenue':300}]}]
out['false_negated_trend']={'text':'营业收入并非逐年增长。','source':source,'issues':dd_verify.check('营业收入并非逐年增长。',source)}
source2=[{'opinionRiskScore':100,'rawRiskFacts':{'public_opinion_score':48}}]
out['wrong_score_semantics']={'text':'原始舆情评分为100分。','source':source2,'issues':dd_verify.check('原始舆情评分为100分。',source2)}
from app.tools.dd_calc import scan_public_opinion
from app.tools.dd_config import load_config
bundle={'basic':{'enterprise_id':'JUDGE_FUTURE'},'opinions':[{'event_id':'JUDGE_EVENT','event_date':'2030-01-01','sentiment':'负面','impact_level':'重大','event_type':'行政处罚','event_content':'未来事件'}],'lawsuits':[]}
out['future_event']={'asOf':'2024-03-15','eventDate':'2030-01-01','result':scan_public_opinion(bundle,load_config('opinion.yaml'),'2024-03-15')}
(root/'docs/10-strategy/AI评委证据-20261025/probe-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))
