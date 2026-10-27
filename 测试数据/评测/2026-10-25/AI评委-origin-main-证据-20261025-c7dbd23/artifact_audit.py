"""只读检查固定远端快照中的提交实物；不输出凭据或联系人原值。"""
from pathlib import Path
import json,csv,io,struct,re,subprocess,os
import yaml
from pypdf import PdfReader
root=Path('/tmp/ocft-origin-main-judge-20261025-c7dbd23')
out=Path(__file__).parent
result={}
manifest=yaml.safe_load((root/'submission/dd04/manifest.generated.yaml').read_text())
result['manifest']={'commit':manifest['code']['commit_sha'],'isPrivate':manifest['code']['is_private'],'realDataUsed':manifest['datasets_used']['real_data_used'],'networkRequired':manifest['demo_env']['network_required'],'primaryPhoneComplete':manifest['contact']['primary_phone'] not in ('TBD','',None),'primaryEmailComplete':manifest['contact']['primary_email'] not in ('TBD','',None),'externalOfflineFallbacks':{s['name']:s['offline_fallback'] for s in manifest['external_services']}}
result['pdfs']=[]
for p in sorted((root/'submission/dd04/artifacts').glob('*.pdf')):
 r=PdfReader(p)
 sizes=[(round(float(pg.mediabox.width),2),round(float(pg.mediabox.height),2)) for pg in r.pages]
 text='\n'.join(pg.extract_text() or '' for pg in r.pages)
 candidates=[p.with_suffix('.md')]
 if '技术方案' in p.name:candidates.append(root/'submission/dd04/技术方案.md')
 if '测试报告' in p.name:candidates.append(root/'submission/dd04/测试报告.md')
 result['pdfs'].append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'pages':len(r.pages),'pageSizesPt':list(dict.fromkeys(sizes)),'encrypted':r.is_encrypted,'mdSourceExists':any(c.exists() for c in candidates),'mdSameDirectorySameName':p.with_suffix('.md').exists(),'textCharacters':len(text),'baseVersionsFound':sorted(set(re.findall(r'00e905f\w*|f711b78\w*',text)))})
 (out/(p.stem+'.extracted.txt')).write_text(text)
result['screenshots']=[]
for p in sorted((root/'测试数据/评测/2026-10-25/a5-walkthrough/M4').glob('*.png')):
 b=p.read_bytes();w,h=struct.unpack('>II',b[16:24])
 result['screenshots'].append({'path':str(p.relative_to(root)),'width':w,'height':h,'bytes':len(b),'sizePass':w>=1280 and h>=720 and len(b)<=5*1024*1024})
result['packScriptSourceExists']={str(p.relative_to(root)):p.exists() for p in [root/'docs/60-pitch/演示脚本.md',root/'docs/60-pitch/赛题04演示脚本.md',*(root/'submission/dd04/artifacts'/n for n in ['截图01_尽调报告_完整.png','截图02_财务分析.png','截图03_风险提示与反欺诈.png'])]}
result['csvs']=[]
for p in sorted((root/'系统输出').glob('*.csv')):
 b=p.read_bytes();rows=list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
 result['csvs'].append({'path':str(p.relative_to(root)),'bom':b.startswith(b'\xef\xbb\xbf'),'rows':len(rows),'headers':list(rows[0]) if rows else [],'applicationIds':[r.get('application_id') for r in rows]})
p=root/'系统输出/智算先锋队_赛题04_非公开测评集结果.csv'
q=root/'系统输出/非公开测评集结果-演练衍生.csv'
result['formalPrivateEqualsRehearsal']=p.read_bytes()==q.read_bytes()
result['videoFiles']=[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size} for p in (root/'submission').rglob('*.mp4')]
result['offlineDependencyFiles']=[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size} for p in (root/'vendor').rglob('*') if p.is_file() and p.suffix in ('.zip','.whl')]
result['lineEndingCounts']={}
for ext in ('.py','.ts','.tsx','.json','.yaml','.md','.ps1'):
 files=[p for p in root.rglob('*'+ext) if 'node_modules' not in p.parts and '.venv' not in p.parts]
 crlf=[str(p.relative_to(root)) for p in files if b'\r\n' in p.read_bytes()]
 result['lineEndingCounts'][ext]={'files':len(files),'crlfCount':len(crlf),'examples':crlf[:8]}
(out/'artifact-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='offlineDependencyFiles'},ensure_ascii=False,indent=2))
