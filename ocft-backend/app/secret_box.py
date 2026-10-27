"""敏感配置加解密 — 密文可入库，主密钥只在本机。

用法（cwd=ocft-backend）：
    生成主密钥（团队一人生成后私下分发）：python -m app.secret_box init
    加密一个值：                          python -m app.secret_box encrypt
    在 .env 里写：                  LLM_API_KEY=enc:gAAAAA...
                                    DATABASE_URL=enc:gAAAAA...

@why 密文与主密钥必须分离：密文（enc:...）可以放进 .env 甚至仓库，
     主密钥只从环境变量 OCFT_MASTER_KEY 或本机密钥文件读取，永不入库。
     算法：Fernet（AES-128-CBC + HMAC-SHA256，带完整性校验），密钥错误或
     密文被篡改时显式报错，不静默回退成明文。
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

PREFIX = "enc:"
KEY_ENV = "OCFT_MASTER_KEY"
KEY_FILE_ENV = "OCFT_MASTER_KEY_FILE"
DEFAULT_KEY_FILE = Path.home() / ".ocft" / "master.key"


class SecretError(RuntimeError):
    """主密钥缺失、密钥不匹配或密文损坏。"""


def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(_load_key())


# 仓库内主密钥（ocft-backend/master.key）。比赛期间随私有仓库提交，保证克隆即可用；
# 赛后删除并轮换（2026-10-22 团队决策，见开发日志）
REPO_KEY_FILE = Path(__file__).resolve().parents[1] / "master.key"


def _key_file() -> Path:
    """查找顺序：OCFT_MASTER_KEY_FILE 指定的文件 > ~/.ocft/master.key > 仓库内 master.key。"""
    explicit = os.environ.get(KEY_FILE_ENV)
    if explicit:
        return Path(explicit)
    if DEFAULT_KEY_FILE.exists() or not REPO_KEY_FILE.exists():
        return DEFAULT_KEY_FILE
    return REPO_KEY_FILE


def _load_key() -> bytes:
    key = os.environ.get(KEY_ENV)
    if key:
        return key.strip().encode()
    path = _key_file()
    if path.exists():
        return path.read_text(encoding="utf-8").strip().encode()
    raise SecretError(
        f"配置中有加密值，但找不到主密钥：请设置环境变量 {KEY_ENV}，"
        f"或把密钥放到 {path}（运行 python -m app.secret_box init 生成）")


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def decrypt(value: str) -> str:
    """enc: 前缀的值解密；其他值原样返回（兼容本地明文开发）。"""
    if not is_encrypted(value):
        return value
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode()).decode("utf-8")
    except InvalidToken as exc:
        raise SecretError("密文无法解密：主密钥不匹配或密文已损坏") from exc


def encrypt(plaintext: str) -> str:
    return PREFIX + _fernet().encrypt(plaintext.encode("utf-8")).decode()


def mask(value: str | None) -> str:
    """日志/错误信息中展示敏感值时只露首尾。"""
    if not value:
        return ""
    return value[:3] + "***" + value[-2:] if len(value) > 8 else "***"


def _cmd_init() -> None:
    from cryptography.fernet import Fernet
    path = _key_file()
    if path.exists():
        print(f"主密钥已存在：{path}（不覆盖）")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(Fernet.generate_key().decode(), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    print(f"已生成主密钥：{path}")
    print("团队共享：通过私聊/密码管理器分发该文件内容，不要提交到仓库或发到群里。")


def _cmd_encrypt() -> None:
    # @why getpass 不回显、不进 shell 历史；也支持管道输入便于脚本化
    plaintext = sys.stdin.readline().rstrip("\n") if not sys.stdin.isatty() \
        else getpass.getpass("输入要加密的值（不回显）：")
    if not plaintext:
        raise SystemExit("值为空，未加密")
    print(encrypt(plaintext))


def main() -> None:
    commands = {"init": _cmd_init, "encrypt": _cmd_encrypt}
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("用法: python -m app.secret_box init | encrypt", file=sys.stderr)
        raise SystemExit(2)
    try:
        commands[sys.argv[1]]()
    except SecretError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
