"""config.yaml 解析与 db.redis 常用操作：环境变量展开、密码转义、未知字段报错、前缀隔离。

@why Redis 用 fakeredis 内存实现，不依赖本机 redis-server；未安装时整体跳过。
"""
import pytest

from db import config as db_config
from db.config import ConfigError, database_url_from_config, load_config, redis_settings

fakeredis = pytest.importorskip("fakeredis")

from db.redis import RedisOps, ping  # noqa: E402


@pytest.fixture
def ops():
    return RedisOps(client=fakeredis.FakeRedis(decode_responses=True), key_prefix="t:")


def test_env_reference_and_default(monkeypatch, tmp_path):
    file = tmp_path / "c.yaml"
    file.write_text("redis:\n  host: ${T_REDIS_HOST:-10.0.0.1}\n  port: ${T_REDIS_PORT}\n"
                    "  ssl: ${T_REDIS_SSL:-false}\n", encoding="utf-8")
    monkeypatch.delenv("T_REDIS_HOST", raising=False)
    monkeypatch.setenv("T_REDIS_PORT", "6380")
    s = redis_settings(load_config(file))
    assert (s.host, s.port, s.ssl) == ("10.0.0.1", 6380, False)


def test_missing_file_returns_empty(tmp_path):
    assert load_config(tmp_path / "absent.yaml") == {}


def test_database_url_escapes_password():
    url = database_url_from_config({"database": {
        "host": "db.example", "port": 3306, "username": "u",
        "password": "p@ss:/#", "name": "ai_marathon"}})
    assert url == "mysql+pymysql://u:p%40ss%3A%2F%23@db.example:3306/ai_marathon"


def test_database_url_unset_returns_none():
    assert database_url_from_config({"database": {"url": "", "host": ""}}) is None


def test_enc_value_is_decrypted(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet

    from app import secret_box
    monkeypatch.setenv(secret_box.KEY_ENV, Fernet.generate_key().decode())
    token = secret_box.encrypt("s3cret")
    file = tmp_path / "c.yaml"
    file.write_text(f"redis:\n  password: \"{token}\"\n", encoding="utf-8")
    assert redis_settings(load_config(file)).password == "s3cret"


def test_unknown_and_bad_type_fail_loudly():
    with pytest.raises(ConfigError):
        redis_settings({"redis": {"hots": "x"}})
    with pytest.raises(ConfigError):
        redis_settings({"redis": {"port": "abc"}})


def test_shipped_config_parses():
    # @why 只校验结构不展开：真实配置含 enc: 密文，没有主密钥的机器上也要能跑
    import yaml

    raw = yaml.safe_load(db_config.DEFAULT_CONFIG_FILE.read_text(encoding="utf-8"))
    assert {"database", "redis"} <= set(raw)
    known = set(db_config.RedisSettings.__dataclass_fields__)
    assert set(raw["redis"]) <= known


def test_string_json_counter_ttl(ops):
    assert ops.set("a", "1", ex=60)
    assert ops.set("a", "2", nx=True) is False
    assert ops.get("a") == "1" and 0 < ops.ttl("a") <= 60
    assert ops.client.get("t:a") == "1"          # 实际 key 带前缀
    assert ops.incr("n", 5) == 5 and ops.decr("n") == 4
    ops.set_json("j", {"中文": [1, 2]})
    assert ops.get_json("j") == {"中文": [1, 2]}
    assert ops.delete("a", "j") == 2 and not ops.exists("a")


def test_get_or_set_caches(ops):
    calls = []
    loader = lambda: calls.append(1) or {"v": 1}  # noqa: E731
    assert ops.get_or_set("c", loader, ex=10) == {"v": 1}
    assert ops.get_or_set("c", loader, ex=10) == {"v": 1}
    assert len(calls) == 1


def test_collections_and_scan(ops):
    ops.hset("h", {"f": "1"})
    assert ops.hgetall("h") == {"f": "1"} and ops.hget("h", "f") == "1"
    ops.rpush("l", "a", "b")
    assert ops.lrange("l") == ["a", "b"] and ops.lpop("l") == "a"
    ops.sadd("s", "x", "y")
    assert ops.smembers("s") == {"x", "y"} and ops.sismember("s", "x")
    ops.zadd("z", {"m1": 2, "m2": 1})
    assert ops.zrange("z") == ["m2", "m1"] and ops.zscore("z", "m1") == 2
    assert sorted(ops.scan_keys("*")) == ["h", "l", "s", "z"]


def test_lock(ops):
    # @why redis-py 锁释放走 Lua（EVALSHA），fakeredis 需 lupa 才支持；未安装时跳过而非误报
    pytest.importorskip("lupa")
    with ops.lock("job", timeout=5):
        assert ops.client.exists("t:lock:job")
    assert not ops.client.exists("t:lock:job")


def test_ping(ops):
    assert ping(ops.client) is True


def test_health_ready_redis_down_is_not_ready(client, monkeypatch):
    # @why Redis 与数据库同级：不通即整体 503，原因里点名 redis
    from app import main
    monkeypatch.setattr(main, "redis_ping", lambda: False)
    res = client.get("/api/health/ready")
    body = res.json()
    assert res.status_code == 503
    assert body["checks"]["redis"] == {"ok": False}
    assert "redis" in body["reason"]


def test_health_ready_redis_up(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "redis_ping", lambda: True)
    body = client.get("/api/health/ready").json()
    assert body["checks"]["redis"] == {"ok": True}
    assert "redis" not in body.get("reason", "")
