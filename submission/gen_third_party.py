"""生成第三方组件清单（名称 / 版本 / License / 用途 / 来源）。

《通用提交材料说明》可选材料 7 与 manifest.third_party_components。
后端：从 ocft-backend/requirements.txt 出发，沿已安装包的元数据求运行时依赖闭包（不含测试依赖）。
前端：ocft-starter/package.json 的 dependencies（打进 dist 的运行时库）与 devDependencies（仅构建期）。
License 一律读安装后的包元数据，读不到的写"未声明"，不手工猜。

用法（仓库根目录，用后端虚拟环境的 Python）：
    ocft-backend/.venv/Scripts/python.exe submission/gen_third_party.py
输出：submission/第三方组件.md、submission/third_party_components.yaml（粘贴进 manifest.yaml）
"""
from __future__ import annotations

import json
import re
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
BACKEND_REQ = ROOT / "ocft-backend" / "requirements.txt"
FRONTEND = ROOT / "ocft-starter"
OUT_MD = ROOT / "submission" / "第三方组件.md"
OUT_YAML = ROOT / "submission" / "third_party_components.yaml"

# 直接依赖的用途说明（与 docs/20-architecture/自研边界与依赖清单.md 一致）；传递依赖统一写"传递依赖"
USAGE = {
    "fastapi": "HTTP 框架", "uvicorn": "ASGI 服务器", "sqlalchemy": "ORM / 数据库访问",
    "pydantic": "请求 / 响应模型校验", "pydantic-settings": "配置加载",
    "openai": "以 OpenAI 兼容协议调用 deepseek-v4.1-flash（只负责 HTTP 传输）",
    "socksio": "SOCKS 代理连接支持", "pymysql": "MySQL 驱动",
    "cryptography": "解密 .env 中的密文配置", "sqlglot": "sql_query 工具的 SQL 语法树只读校验",
    "langgraph": "调度 model / tools 两个节点的下一跳（ADR-0004）",
    "langchain-core": "LangGraph 的依赖，本仓库不直接调用", "openpyxl": "批量测评读写 xlsx",
    "redis": "Redis 客户端", "pyyaml": "读取 config.yaml",
    "react": "UI 框架", "react-dom": "UI 渲染", "echarts": "运行看板图表", "motion": "轨迹入场动效",
    "lucide-react": "图标", "@base-ui/react": "无样式组件底座", "tailwindcss": "样式",
    "@tailwindcss/vite": "Tailwind 构建插件", "class-variance-authority": "组件变体样式",
    "cn": "class 合并工具", "shadcn": "组件样式工具", "tw-animate-css": "组件动画类",
    "vite": "前端构建", "@vitejs/plugin-react": "React 构建插件", "typescript": "类型检查",
    "oxlint": "代码检查", "@types/react": "类型声明", "@types/react-dom": "类型声明",
    "@types/node": "类型声明",
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _license(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr.strip()
    raw = (meta.get("License") or "").strip()
    if raw.upper() in ("UNKNOWN", "NONE"):
        raw = ""
    if raw and "\n" not in raw and len(raw) <= 60:
        return raw
    classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or []
                   if c.startswith("License ::") and "OSI Approved" in c]
    if classifiers:
        return " / ".join(classifiers)
    return raw.splitlines()[0][:60] if raw else "未声明"


def _source(dist: metadata.Distribution) -> str:
    for entry in dist.metadata.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("source", "source code", "repository", "homepage", "github"):
            return url.strip()
    return dist.metadata.get("Home-page") or f"https://pypi.org/project/{dist.metadata['Name']}/"


def python_components() -> list[dict]:
    env = default_environment()
    direct = []
    for line in BACKEND_REQ.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            direct.append(Requirement(line))
    seen: dict[str, dict] = {}
    queue = [(req, True) for req in direct]
    while queue:
        req, is_direct = queue.pop(0)
        key = _norm(req.name)
        if key in seen:
            continue
        try:
            dist = metadata.distribution(req.name)
        except metadata.PackageNotFoundError:
            raise SystemExit(f"{req.name} 未安装：请先 pip install -r ocft-backend/requirements.txt")
        seen[key] = {
            "name": dist.metadata["Name"], "version": dist.version, "license": _license(dist),
            "usage": USAGE.get(key, "传递依赖"), "source": _source(dist),
            "scope": "后端运行时" + ("（直接依赖）" if is_direct else ""),
        }
        for child in dist.requires or []:
            child_req = Requirement(child)
            extras = req.extras or {""}
            if child_req.marker and not any(
                    child_req.marker.evaluate({**env, "extra": e}) for e in extras):
                continue
            queue.append((child_req, False))
    return sorted(seen.values(), key=lambda c: (not c["scope"].endswith("（直接依赖）"), c["name"].lower()))


def node_components() -> list[dict]:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    out = []
    for group, scope in (("dependencies", "前端运行时（打包进 dist）"), ("devDependencies", "前端构建期")):
        for name, version in package.get(group, {}).items():
            meta_path = FRONTEND / "node_modules" / name / "package.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            lic = meta.get("license")
            if isinstance(lic, dict):
                lic = lic.get("type")
            repo = meta.get("repository")
            if isinstance(repo, dict):
                repo = repo.get("url")
            out.append({"name": name, "version": meta.get("version", version), "license": lic or "未声明",
                        "usage": USAGE.get(name, ""), "scope": scope,
                        "source": (repo or f"https://www.npmjs.com/package/{name}").removeprefix("git+")})
    return out


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # JSON 字符串即合法 YAML 双引号字符串


def main() -> None:
    components = python_components() + node_components()
    lines = [
        "# 第三方组件清单",
        "",
        "> 由 `submission/gen_third_party.py` 生成，请勿手改；依赖变化后重新生成。",
        "> 后端为 `ocft-backend/requirements.txt` 的运行时依赖闭包（不含 pytest 等测试依赖），"
        "前端为 `ocft-starter/package.json` 的直接依赖。License 读自安装后的包元数据。",
        "",
        "| 组件 | 版本 | License | 用途 | 范围 | 来源 |",
        "|------|------|---------|------|------|------|",
    ]
    for c in components:
        lines.append(f"| {c['name']} | {c['version']} | {c['license']} | {c['usage']} | {c['scope']} | {c['source']} |")
    unknown = [c["name"] for c in components if c["license"] == "未声明"]
    lines += ["", f"共 {len(components)} 项。" + (f"License 未在元数据中声明、需人工核对：{', '.join(unknown)}。" if unknown else "")]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    yaml = ["# 粘贴到 manifest.yaml 的 third_party_components 字段（由 gen_third_party.py 生成）",
            "third_party_components:"]
    for c in components:
        yaml += [f"  - name: {_yaml_str(c['name'])}", f"    version: {_yaml_str(c['version'])}",
                 f"    license: {_yaml_str(c['license'])}",
                 f"    usage: {_yaml_str(c['usage'] or c['scope'])}"]
    OUT_YAML.write_text("\n".join(yaml) + "\n", encoding="utf-8")
    print(f"已生成 {OUT_MD.relative_to(ROOT)}（{len(components)} 项）与 {OUT_YAML.relative_to(ROOT)}")
    if unknown:
        print("需人工核对 License：" + ", ".join(unknown))


if __name__ == "__main__":
    main()
