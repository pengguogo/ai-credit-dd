"""数据层连接配置 — 从 ocft-backend/config.yaml 读取数据库、Redis 等连接信息。

用法：
    from db.config import load_config, database_url_from_config, redis_settings

@why 连接信息集中在一个 YAML，换环境只改一处；敏感值不落明文：
     字符串值支持 ${ENV} / ${ENV:-默认值} 引用环境变量，以及 enc: 密文
     （app/secret_box.py 解密，主密钥缺失或不匹配时显式报错）。
     文件路径可用环境变量 OCFT_DB_CONFIG 覆盖，便于测试与多环境切换。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

CONFIG_ENV = "OCFT_DB_CONFIG"
# @why 配置放后端根目录而非 db/ 内：同一文件后续还要承载其他模块的配置段
DEFAULT_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yaml"
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


class ConfigError(RuntimeError):
    """配置文件格式错误、字段未知或类型不合法。"""


@dataclass(frozen=True)
class RedisSettings:
    url: str = ""
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    username: str = ""
    password: str = ""
    ssl: bool = False
    key_prefix: str = "ocft:"
    socket_timeout: float = 3.0
    socket_connect_timeout: float = 3.0
    max_connections: int = 20
    decode_responses: bool = True


def config_path() -> Path:
    return Path(os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG_FILE)


def _expand(value: Any) -> Any:
    """递归替换 ${ENV} 引用并解密 enc: 值。"""
    from app.secret_box import decrypt

    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, str):
        expanded = _ENV_REF.sub(
            lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)
        return decrypt(expanded)
    return value


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """读取并展开配置；文件不存在时返回空字典（调用方走各自的默认值）。"""
    file = Path(path) if path else config_path()
    if not file.exists():
        return {}
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ConfigError("读取 config.yaml 需要 PyYAML：pip install -r requirements.txt") from exc
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件 {file} 不是合法 YAML：{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件 {file} 顶层必须是映射")
    return _expand(data)


def database_url_from_config(config: dict[str, Any] | None = None) -> str | None:
    """返回 database 段的连接串；未配置（url 与 host 都为空）时返回 None。"""
    section = (load_config() if config is None else config).get("database") or {}
    url = str(section.get("url") or "").strip()
    if url:
        return url
    host = str(section.get("host") or "").strip()
    if not host:
        return None
    from sqlalchemy.engine import URL

    # @why URL.create 负责转义密码中的 @ : / # 等字符，避免手拼连接串出错
    port = section.get("port")
    return URL.create(
        drivername=str(section.get("driver") or "mysql+pymysql"),
        username=str(section.get("username") or "") or None,
        password=str(section.get("password") or "") or None,
        host=host,
        port=int(port) if port not in (None, "") else None,
        database=str(section.get("name") or "") or None,
    ).render_as_string(hide_password=False)


def _coerce(name: str, value: Any, default: Any) -> Any:
    """按默认值类型转换：${ENV} 展开后都是字符串，需转回 int / float / bool。"""
    try:
        if isinstance(default, bool):
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in _TRUE:
                return True
            if text in _FALSE:
                return False
            raise ValueError(value)
        if isinstance(default, int):
            return int(value)
        if isinstance(default, float):
            return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"redis.{name} 的值 {value!r} 类型不合法") from exc
    return "" if value is None else str(value)


def redis_settings(config: dict[str, Any] | None = None) -> RedisSettings:
    """解析 redis 段；未知字段直接报错，防止拼写错误被静默忽略。"""
    section = (load_config() if config is None else config).get("redis") or {}
    known = {f.name: f.default for f in fields(RedisSettings)}
    unknown = sorted(set(section) - set(known))
    if unknown:
        raise ConfigError(f"redis 段存在未知字段：{unknown}")
    return RedisSettings(**{
        name: _coerce(name, value, known[name]) for name, value in section.items()})
