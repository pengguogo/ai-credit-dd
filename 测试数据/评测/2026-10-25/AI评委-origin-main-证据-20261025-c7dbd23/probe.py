"""评委故障注入探针：临时SQLite＋假模型，无真实模型费用，不改变业务源码。"""
import os,sys,tempfile,json
from pathlib import Path
root=Path('/tmp/ocft-origin-main-judge-20261025-c7dbd23'); backend=root/'ocft-backend'
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

from app.compliance.citations import check_regulation_citations
claim='依据《评委合成测试条例》第九条，所有企业必须无条件获得贷款。'
sources=['事件标题：提及《评委合成测试条例》第九条。此处不提供任何授信条文内容。']
decision=check_regulation_citations(claim,sources)
out['unsupported_law_content_with_matching_title']={'claim':claim,'source':sources,'isClean':decision.is_clean,'scope':'仅探测条文正文蕴含校验；名称与条号均为人工合成'}
captured=[]
def capture_unseen(messages,*a,**k):
 text=json.dumps(messages,ensure_ascii=False)
 captured.append({'unknownCompanyUnmasked':'测试城云端演练科技有限公司' in text,'unknownPersonUnmasked':'欧阳演练' in text})
 return {'content':'请提供企业编号以便核验。','tool_calls':[],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2},'model':'deepseek-v4.1-flash','finish_reason':'stop'}
llm.complete_with_tools=capture_unseen
with TestClient(app) as client:
 r=client.post('/api/agent/runs',json={'question':'请分析测试城云端演练科技有限公司的偿债能力，法定代表人为欧阳演练。','scenarioId':'enterprise_dd'},headers={'X-Actor-Id':'judge_unseen_privacy'})
 out['unseen_sensitive_input']={'httpStatus':r.status_code,'modelBoundaryCalls':captured,'scope':'公司与人名均为合成；假模型替换网络边界，未向外部服务发送'}


from app.db import SessionLocal
from app.tools.registry import execute_tool
from app.agent.scenarios import SCENARIOS
sql='WITH t(c0,c1,c2,c3,c4,c5,c6,rating_hint,c8) AS (SELECT * FROM enterprise_risk) SELECT c1 AS enterprise_id, rating_hint FROM t LIMIT 10'
with SessionLocal() as db:
 result,records,args=execute_tool(db,{'run_id':'judge_alias','data_version':1,'sql_tables':SCENARIOS['enterprise_dd'].sql_tables},'sql_query',json.dumps({'sql':sql}))
 out['sql_cte_alias_label_leak']={'sql':sql,'toolSuccess':result.is_success,'data':result.data,'error':str(result.error),'evidenceRecords':len(records),'sqlDeclaredToController':'sql_query' in SCENARIOS['enterprise_dd'].allowed_tools}

Path('/Users/dawn/ai马拉松/测试数据/评测/2026-10-25/AI评委-origin-main-证据-20261025-c7dbd23/probe-result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))
