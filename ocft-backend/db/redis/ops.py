"""Redis 常用操作 — 字符串 / JSON / 计数 / 过期 / Hash / List / Set / ZSet / 分布式锁 / 缓存。

@why 统一加 key 前缀（配置 redis.key_prefix）：多项目共用一个实例时互不覆盖；
     对外参数与返回值都用不带前缀的业务 key，调用方无需关心前缀。
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from typing import Any

import redis as redis_lib
from redis.lock import Lock

from db.config import redis_settings

from .client import get_redis


class RedisOps:
    def __init__(self, client: redis_lib.Redis | None = None,
                 key_prefix: str | None = None) -> None:
        self.client = client or get_redis()
        self.prefix = key_prefix if key_prefix is not None else redis_settings().key_prefix

    def key(self, name: str) -> str:
        return f"{self.prefix}{name}"

    # ---- 通用 ----
    def exists(self, name: str) -> bool:
        return bool(self.client.exists(self.key(name)))

    def delete(self, *names: str) -> int:
        if not names:
            return 0
        return int(self.client.delete(*(self.key(n) for n in names)))

    def expire(self, name: str, seconds: int) -> bool:
        return bool(self.client.expire(self.key(name), seconds))

    def ttl(self, name: str) -> int:
        """剩余秒数；-1 表示永不过期，-2 表示 key 不存在。"""
        return int(self.client.ttl(self.key(name)))

    def scan_keys(self, pattern: str = "*", count: int = 500) -> Iterator[str]:
        """按模式遍历 key（SCAN，不阻塞实例；禁止用 KEYS）。返回不带前缀的 key。"""
        for raw in self.client.scan_iter(match=self.key(pattern), count=count):
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            yield text[len(self.prefix):]

    # ---- 字符串 / 计数 ----
    def get(self, name: str) -> Any:
        return self.client.get(self.key(name))

    def set(self, name: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        """ex 为过期秒数；nx=True 时仅在 key 不存在时写入，返回是否写入成功。"""
        return bool(self.client.set(self.key(name), value, ex=ex, nx=nx))

    def incr(self, name: str, amount: int = 1) -> int:
        return int(self.client.incrby(self.key(name), amount))

    def decr(self, name: str, amount: int = 1) -> int:
        return int(self.client.decrby(self.key(name), amount))

    # ---- JSON ----
    def get_json(self, name: str) -> Any:
        raw = self.get(name)
        return None if raw is None else json.loads(raw)

    def set_json(self, name: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        return self.set(name, json.dumps(value, ensure_ascii=False), ex=ex, nx=nx)

    def get_or_set(self, name: str, loader: Callable[[], Any], ex: int | None = None) -> Any:
        """缓存旁路：命中直接返回，未命中调用 loader 并写入缓存（None 不缓存）。"""
        cached = self.get_json(name)
        if cached is not None:
            return cached
        value = loader()
        if value is not None:
            self.set_json(name, value, ex=ex)
        return value

    # ---- Hash ----
    def hset(self, name: str, mapping: Mapping[str, Any]) -> int:
        return int(self.client.hset(self.key(name), mapping=dict(mapping)))

    def hget(self, name: str, field: str) -> Any:
        return self.client.hget(self.key(name), field)

    def hgetall(self, name: str) -> dict:
        return dict(self.client.hgetall(self.key(name)))

    def hdel(self, name: str, *fields: str) -> int:
        return int(self.client.hdel(self.key(name), *fields))

    # ---- List ----
    def lpush(self, name: str, *values: Any) -> int:
        return int(self.client.lpush(self.key(name), *values))

    def rpush(self, name: str, *values: Any) -> int:
        return int(self.client.rpush(self.key(name), *values))

    def lpop(self, name: str) -> Any:
        return self.client.lpop(self.key(name))

    def rpop(self, name: str) -> Any:
        return self.client.rpop(self.key(name))

    def lrange(self, name: str, start: int = 0, end: int = -1) -> list:
        return list(self.client.lrange(self.key(name), start, end))

    # ---- Set ----
    def sadd(self, name: str, *members: Any) -> int:
        return int(self.client.sadd(self.key(name), *members))

    def srem(self, name: str, *members: Any) -> int:
        return int(self.client.srem(self.key(name), *members))

    def smembers(self, name: str) -> set:
        return set(self.client.smembers(self.key(name)))

    def sismember(self, name: str, member: Any) -> bool:
        return bool(self.client.sismember(self.key(name), member))

    # ---- Sorted Set ----
    def zadd(self, name: str, mapping: Mapping[str, float]) -> int:
        return int(self.client.zadd(self.key(name), dict(mapping)))

    def zrange(self, name: str, start: int = 0, end: int = -1,
               withscores: bool = False, desc: bool = False) -> list:
        return list(self.client.zrange(self.key(name), start, end,
                                       desc=desc, withscores=withscores))

    def zscore(self, name: str, member: str) -> float | None:
        return self.client.zscore(self.key(name), member)

    def zrem(self, name: str, *members: str) -> int:
        return int(self.client.zrem(self.key(name), *members))

    # ---- 分布式锁 ----
    def lock(self, name: str, timeout: float = 30,
             blocking_timeout: float | None = 10) -> Lock:
        """返回可用作 with 语句的锁；timeout 为锁自动过期秒数，防止持有者崩溃后死锁。

        获取超时时 with 语句抛出 redis.exceptions.LockError。
        """
        return self.client.lock(self.key(f"lock:{name}"), timeout=timeout,
                                blocking_timeout=blocking_timeout)
