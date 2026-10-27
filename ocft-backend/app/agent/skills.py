"""运行时 Skill：每个尽调角色 Agent 的输入契约与输出规则，在该角色调用模型时拼进 system 消息。

Skill 文件是 Markdown，带 YAML front matter，放在场景包里（scenarios/dd04/skills/*.md）：
name / title / version / role / roles / inputs / outputs，正文是解读与成文规则。
roles 填 agents.yaml 里的角色键（business / finance / opinion / fraud / rating / report）。

@why 角色提示词（prompts/*.md）只写职责与判断边界，模型拿到的仍是计算结果 JSON，
     数值换算、措辞和版式全靠模型自己把握，同一输入多次运行输出会漂移。Skill 把这些写成
     版本化的固定规则，随角色调用一起下发；改写法只改 Skill，不改代码。
     Skill 只规定怎么读、怎么写，不含任何题目数据或结论（红线 3）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)
_REQUIRED = ("name", "title", "version", "role", "roles", "inputs", "outputs")

SKILL_DIR = Path(__file__).resolve().parents[2] / "scenarios" / "dd04" / "skills"


class SkillError(RuntimeError):
    """Skill 文件缺失、格式错误或字段不全。加载时直接失败，不带病运行。"""


@dataclass(frozen=True)
class Skill:
    name: str
    title: str
    version: str
    role: str
    roles: tuple[str, ...]
    inputs: str
    outputs: str
    rules: str
    source: str

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def prompt(self) -> str:
        """拼进角色 system 消息的文本。"""
        return (f"# Skill：{self.title}（{self.ref}）\n"
                f"输入：{self.inputs}\n输出：{self.outputs}\n\n{self.rules}")


def parse_skill(text: str, source: str) -> Skill:
    match = _FRONT_MATTER.match(text.lstrip("\ufeff"))
    if not match:
        raise SkillError(f"{source}: 缺少 --- 包围的 front matter")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"{source}: front matter 不是合法 YAML：{exc}") from exc
    if not isinstance(meta, dict):
        raise SkillError(f"{source}: front matter 必须是映射")
    missing = [key for key in _REQUIRED if not meta.get(key)]
    if missing:
        raise SkillError(f"{source}: 缺少字段 {missing}")
    roles = meta["roles"]
    if not isinstance(roles, list) or not all(isinstance(r, str) and r for r in roles):
        raise SkillError(f"{source}: roles 必须是非空字符串列表")
    rules = match.group(2).strip()
    if not rules:
        raise SkillError(f"{source}: 正文规则为空")
    return Skill(name=str(meta["name"]), title=str(meta["title"]), version=str(meta["version"]),
                 role=str(meta["role"]), roles=tuple(roles),
                 inputs=str(meta["inputs"]).strip(), outputs=str(meta["outputs"]).strip(),
                 rules=rules, source=source)


@lru_cache(maxsize=None)
def load_skills(directory: str, known_roles: tuple[str, ...]) -> dict[str, Skill]:
    """读取目录下全部 *.md，返回 角色键 → Skill。

    名称重复、同一角色被两个 Skill 认领、或 roles 里有未知角色时报错。
    @why 有缓存：角色每次调用都要用，改 Skill 后需重启后端（开发时 uvicorn 加 --reload-include "*.md"）。
    """
    root = Path(directory)
    if not root.is_dir():
        raise SkillError(f"Skill 目录不存在：{root}")
    names: set[str] = set()
    by_role: dict[str, Skill] = {}
    for path in sorted(root.glob("*.md")):
        skill = parse_skill(path.read_text(encoding="utf-8"), path.name)
        if skill.name in names:
            raise SkillError(f"{path.name}: Skill 名称 {skill.name} 重复")
        names.add(skill.name)
        for role in skill.roles:
            if role not in known_roles:
                raise SkillError(f"{path.name}: 未知角色 {role}，可选 {list(known_roles)}")
            if role in by_role:
                raise SkillError(f"{path.name}: 角色 {role} 已由 {by_role[role].name} 认领")
            by_role[role] = skill
    if not by_role:
        raise SkillError(f"Skill 目录为空：{root}")
    return by_role
