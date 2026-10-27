"""Redis 连接 — 按 ocft-backend/config.yaml 的 redis 段创建带连接池的客户端。

@why 客户端自带连接池且线程安全：进程内用一个单例（get_redis），
     避免每次操作新建 TCP 连接；测试或多实例场景用 create_client 显式构建。
"""
from __future__ import annotations

import threading

import redis as redis_lib

from db.config import RedisSettings, redis_settings

_lock = threading.Lock()
_client: redis_lib.Redis | None = None


def create_client(settings: RedisSettings | None = None) -> redis_lib.Redis:
    """按配置构建客户端（惰性连接，首次执行命令时才建立 TCP 连接）。"""
    s = settings or redis_settings()
    common = {
        "socket_timeout": s.socket_timeout,
        "socket_connect_timeout": s.socket_connect_timeout,
        "max_connections": s.max_connections,
        "decode_responses": s.decode_responses,
        "health_check_interval": 30,
    }
    if s.url:
        return redis_lib.Redis.from_url(s.url, **common)
    return redis_lib.Redis(
        host=s.host, port=s.port, db=s.db,
        username=s.username or None, password=s.password or None,
        ssl=s.ssl, **common)


def get_redis() -> redis_lib.Redis:
    """进程内单例客户端。"""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = create_client()
    return _client


def close_redis() -> None:
    """释放单例连接池（应用关闭或切换配置时调用）。"""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None


def ping(client: redis_lib.Redis | None = None) -> bool:
    """连通性检查。

    @why 供健康检查使用：连不上是预期内的状态，返回 False 由调用方如实展示；
         只捕获 RedisError，其他异常照常抛出。
    """
    try:
        return bool((client or get_redis()).ping())
    except redis_lib.RedisError:
        return False
