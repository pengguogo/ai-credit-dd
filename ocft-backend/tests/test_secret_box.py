"""密文配置：加解密往返、明文透传、错误密钥与缺失密钥显式失败。"""
import pytest
from cryptography.fernet import Fernet

from app import secret_box
from app.secret_box import SecretError, decrypt, encrypt, is_encrypted


@pytest.fixture
def master_key(monkeypatch, tmp_path):
    monkeypatch.setenv(secret_box.KEY_FILE_ENV, str(tmp_path / "none.key"))
    key = Fernet.generate_key().decode()
    monkeypatch.setenv(secret_box.KEY_ENV, key)
    return key


def test_roundtrip(master_key):
    plain = "mysql+pymysql://user:p%40ss@db.example:3306/ai_marathon"
    token = encrypt(plain)
    assert is_encrypted(token) and plain not in token
    assert decrypt(token) == plain


def test_plaintext_passthrough(master_key):
    assert decrypt("sqlite:///./ocft.db") == "sqlite:///./ocft.db"
    assert decrypt("") == ""


def test_wrong_key_fails_loudly(master_key, monkeypatch):
    token = encrypt("secret-value")
    monkeypatch.setenv(secret_box.KEY_ENV, Fernet.generate_key().decode())
    with pytest.raises(SecretError):
        decrypt(token)


def test_tampered_ciphertext_fails(master_key):
    token = encrypt("secret-value")
    with pytest.raises(SecretError):
        decrypt(token[:-4] + "AAAA")


def test_missing_key_fails(master_key, monkeypatch):
    token = encrypt("secret-value")
    monkeypatch.delenv(secret_box.KEY_ENV)
    with pytest.raises(SecretError, match="主密钥"):
        decrypt(token)


def test_key_file(monkeypatch, tmp_path):
    key_file = tmp_path / "master.key"
    key_file.write_text(Fernet.generate_key().decode(), encoding="utf-8")
    monkeypatch.delenv(secret_box.KEY_ENV, raising=False)
    monkeypatch.setenv(secret_box.KEY_FILE_ENV, str(key_file))
    assert decrypt(encrypt("v")) == "v"


def test_settings_decrypts_llm_key(master_key):
    from app.config import Settings
    settings = Settings(llm_api_key=encrypt("sk-real-key"), _env_file=None)
    assert settings.llm_api_key == "sk-real-key"


def test_repo_key_file_used_when_home_key_missing(monkeypatch, tmp_path):
    """克隆即可用：本机没有 ~/.ocft/master.key 时回退到仓库内 master.key。"""
    repo_key = tmp_path / "repo.key"
    repo_key.write_text(Fernet.generate_key().decode(), encoding="utf-8")
    monkeypatch.delenv(secret_box.KEY_ENV, raising=False)
    monkeypatch.delenv(secret_box.KEY_FILE_ENV, raising=False)
    monkeypatch.setattr(secret_box, "DEFAULT_KEY_FILE", tmp_path / "no-home.key")
    monkeypatch.setattr(secret_box, "REPO_KEY_FILE", repo_key)
    assert secret_box._key_file() == repo_key
    assert decrypt(encrypt("v")) == "v"

    home_key = tmp_path / "no-home.key"
    home_key.write_text(Fernet.generate_key().decode(), encoding="utf-8")
    assert secret_box._key_file() == home_key        # 本机密钥优先
