"""模型配置与错误分类：API 模型 ID 白名单、按状态码分类（不匹配错误文本）。"""
import pytest

from app import llm
from app.config import ALLOWED_API_MODELS, Settings


class _HttpError(Exception):
    def __init__(self, status_code, message="boom"):
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4.1-flash"])
def test_allowed_api_models(model):
    Settings(llm_api_model=model, _env_file=None).validate_runtime()


@pytest.mark.parametrize("model", ["deepseek-v4-pro", "deepseek-chat", "gpt-4o", "deepseek-reasoner"])
def test_other_models_rejected(model):
    with pytest.raises(RuntimeError, match="LLM_API_MODEL"):
        Settings(llm_api_model=model, _env_file=None).validate_runtime()


def test_blank_uses_defaults():
    s = Settings(llm_api_model="", llm_model="", _env_file=None)
    assert s.llm_model == "deepseek-v4.1-flash" and s.llm_api_model in ALLOWED_API_MODELS


def test_product_model_still_locked():
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        Settings(llm_model="deepseek-v4-pro", _env_file=None).validate_runtime()


def test_request_uses_api_model_id(monkeypatch):
    seen = {}

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    raise _HttpError(400)

    monkeypatch.setattr(llm, "_get_client", lambda: _Client)
    with pytest.raises(llm.LLMError):
        llm.complete([{"role": "user", "content": "hi"}])
    assert seen["model"] == llm.settings.llm_api_model


@pytest.mark.parametrize("thinking, expected", [
    (None, None),
    (False, {"thinking": {"type": "disabled"}}),
    (True, {"thinking": {"type": "enabled"}}),
])
def test_thinking_switch_maps_to_extra_body(monkeypatch, thinking, expected):
    # 不传 thinking 时请求体与原来一致；显式开关按 DeepSeek 的 thinking.type 下发
    seen = {}

    class _Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    seen.update(kwargs)
                    raise _HttpError(400)

    monkeypatch.setattr(llm, "_get_client", lambda: _Client)
    with pytest.raises(llm.LLMError):
        llm.complete_with_tools([{"role": "user", "content": "hi"}], [], thinking=thinking)
    assert seen.get("extra_body") == expected


@pytest.mark.parametrize("status, code, retryable", [
    (401, "auth_failed", False), (403, "auth_failed", False),
    (429, "rate_limited", True),
    (400, "bad_request", False), (404, "bad_request", False),
    (500, "unavailable", True), (503, "unavailable", True),
])
def test_error_classified_by_status(status, code, retryable):
    err = llm._to_llm_error(_HttpError(status))
    assert err.code == code and err.is_retryable is retryable


def test_request_id_digits_do_not_cause_misclassification():
    """回归：400 响应文本里 request_id 含 "429" 曾被误判成限流。"""
    err = llm._to_llm_error(_HttpError(400, "(request_id: 6429aa-rate-4291)"))
    assert err.code == "bad_request"
