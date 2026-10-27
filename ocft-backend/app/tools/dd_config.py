"""赛题 04 配置加载。每次调用重新读取，改 yaml 不改代码即可生效。"""
from pathlib import Path

import yaml

from ..domain.errors import ToolError

CONFIG_DIR = Path(__file__).resolve().parents[2] / "scenarios" / "dd04"


def load_config(name: str) -> dict:
    path = CONFIG_DIR / name
    if not path.is_file():
        raise ToolError("execution_failed", f"缺少尽调配置: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ToolError("execution_failed", f"配置 {name} 必须是 YAML 对象")
    data["_file"] = f"scenarios/dd04/{name}"
    return data
