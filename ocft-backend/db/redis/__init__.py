"""db.redis — Redis 连接与常用操作（连接信息见 ocft-backend/config.yaml 的 redis 段）。

用法：
    from db.redis import RedisOps, get_redis, ping

    ops = RedisOps()                       # 默认用进程内单例连接与配置里的 key_prefix
    ops.set_json("session:42", {"a": 1}, ex=600)
    ops.get_json("session:42")
    with ops.lock("job:seed", timeout=30):
        ...

@why 包名 redis 与三方库同名：只能以 db.redis 方式导入；不要把 db/ 目录
     直接加进 sys.path（如 python db/redis/xxx.py），否则会遮蔽三方 redis 库。
"""
from .client import close_redis, create_client, get_redis, ping
from .ops import RedisOps

__all__ = ["RedisOps", "close_redis", "create_client", "get_redis", "ping"]
