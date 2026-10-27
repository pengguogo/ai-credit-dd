import os
import sys
import json
import hashlib
from pathlib import Path

ROOT = Path('/tmp/ocft-judge-fe2e9ae')
os.environ['OCFT_DB_CONFIG'] = '/tmp/ocft-judge-current-review/absent.yaml'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['LLM_API_KEY'] = 'test-key-not-real'
sys.path.insert(0, str(ROOT / 'ocft-backend'))

from app.agent.dd_verify import check
from app.agent.dd_snapshot import Masker
from app.agent import engine, graph
from app.agent.scenarios import Scenario
from app.main import _FrontendFiles
from fastapi import FastAPI
from fastapi.testclient import TestClient

result = {
    'negative_to_positive': check('经营现金流800万元', [{'operatingCashflow': -800}]),
    'wrong_account': check('经营现金流3500万元', [{'operatingCashflow': -800, 'otherReceivables': 3500}]),
}
masker = Masker()
masker.add('测试法人甲', '人员E999-1', restore_on_output=True)
result['name_restore'] = masker.restore_names(masker.mask('法人：测试法人甲'))

# 只截获调度入参，不连接模型、数据库或外部图片。
captured = {}
original = graph.invoke_bounded_loop
def capture(**kwargs):
    captured['messages'] = kwargs['messages']
graph.invoke_bounded_loop = capture
image_url = 'data:image/png;base64,QUJD'
try:
    engine.run(None, scenario=Scenario('probe', 'local probe', [], build_masker=lambda db: masker),
               question='核对测试法人甲资料', history=[], run_ctx={},
               persist_evidence=lambda record: 'unused', attachments=[image_url])
finally:
    graph.invoke_bounded_loop = original
content = captured['messages'][-1]['content']
result['attachment_path'] = {
    'text_masked': '测试法人甲' not in content[0]['text'],
    'image_bytes_unchanged': content[1]['image_url']['url'] == image_url,
    'scope': 'local message capture only; no real personal data, no network call',
}

app = FastAPI()
app.mount('/', _FrontendFiles(directory=ROOT / 'ocft-starter/dist', html=True))
with TestClient(app) as client:
    result['dist_routes'] = {url: client.get(url).status_code for url in
                             ['/', '/report/business?enterpriseId=E001', '/api/unknown']}

batch = ROOT / '测试数据/评测/2026-10-24/official-rerun-c6ab7ff'
record = json.loads((batch / 'start-record.json').read_text())
hashes = record['codeHashes']
changed = [name for name, digest in hashes.items()
           if not (ROOT / name).exists() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
result['existing_eval_hash_check'] = {'checked': len(hashes), 'changed': changed}
result['existing_eval_metrics'] = json.loads((batch / 'metrics.json').read_text())

skip = {'.git', '.venv', 'node_modules', 'vendor', '__pycache__'}
artifacts = []
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [name for name in dirs if name not in skip]
    for name in files:
        path = Path(base) / name
        if path.suffix.lower() in {'.pdf', '.mp4', '.zip', '.png', '.jpg', '.jpeg'}:
            artifacts.append({'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size})
result['artifact_inventory'] = artifacts
Path('/Users/dawn/ai马拉松/docs/10-strategy/已提交版评委证据-fe2e9ae/reproduction.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key: value for key, value in result.items() if key not in
                 {'artifact_inventory', 'existing_eval_metrics'}}, ensure_ascii=False, indent=2))
