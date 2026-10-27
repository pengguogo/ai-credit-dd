import os,runpy,sys
from pathlib import Path
from dotenv import dotenv_values
source=sys.argv.pop(1)
for key,value in dotenv_values(source,interpolate=False).items():
    if value is not None: os.environ[key]=value
sys.path.insert(0,str(Path.cwd()))
from app.config import settings
settings.validate_runtime()
print("环境已加载；模型限制校验通过；凭据不回显",flush=True)
runpy.run_module("eval.run",run_name="__main__")
