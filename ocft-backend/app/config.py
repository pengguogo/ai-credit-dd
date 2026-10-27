"""环境配置 — 运行时模型锁定 + 数据库连接。

@why 比赛规则强制运行时只用 deepseek-v4.1-flash：模型名允许由环境变量覆盖，
     但值不等于锁定值时启动即失败（fail-fast），杜绝静默回退到其他模型。
     环境变量只提供 API 地址与凭据，不提供模型选择。
     LLM_API_KEY / DATABASE_URL 支持 enc: 密文（见 app/secret_box.py）。
"""
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .secret_box import decrypt

# 比赛指定运行时模型，唯一合法值
REQUIRED_MODEL = "deepseek-v4.1-flash"

# 同一模型（V4.1 Flash）在不同接口上的 API 模型 ID；不在白名单内的任何值
# 一律拒绝启动，防止静默换成别的模型
ALLOWED_API_MODELS = frozenset({"deepseek-flash", REQUIRED_MODEL})
DEFAULT_API_MODEL = "deepseek-flash"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    # 产品身份：比赛指定模型，记录在 run 与健康检查中，唯一合法值
    llm_model: str = REQUIRED_MODEL
    # 线上 API 的模型 ID：DeepSeek 公共接口对 V4.1 Flash 使用 deepseek-flash；
    # 若使用主办方提供的接口，按其文档改成 deepseek-v4.1-flash。仅允许白名单内的值。
    llm_api_model: str = DEFAULT_API_MODEL

    @field_validator("llm_model", "llm_api_model", mode="before")
    @classmethod
    def _blank_uses_default(cls, value: object, info) -> object:
        """留空 = 默认值（.env.example 承诺）；显式填其他值由 validate_runtime fail-fast。"""
        if value is None or (isinstance(value, str) and not value.strip()):
            return REQUIRED_MODEL if info.field_name == "llm_model" else DEFAULT_API_MODEL
        return value

    @field_validator("llm_api_key", "database_url", mode="after")
    @classmethod
    def _decrypt_secret(cls, value: str) -> str:
        """enc: 前缀的值在加载时用本机主密钥解密，明文只存在于进程内存。"""
        return decrypt(value)

    llm_timeout_seconds: float = 30.0
    llm_max_tokens_per_request: int = 2048

    # 单次 run 的限制。None 表示不限：比赛规则与赛题 04 都没有轮数、总时限要求，
    # 2026-10-24 起默认取消原 6 轮 / 60 秒（ADR-0008 决策 4）；需要时用环境变量
    # RUN_MAX_TOOL_ROUNDS / RUN_TIMEOUT_SECONDS 设回具体值，机制不变。
    # 不限轮数时仍有两道兜底：累计 token 上限，以及单次模型调用超时 llm_timeout_seconds。
    # token 上限对齐 deepseek-flash 的 1,048,576 上下文（远端 2026-10-24 按实测调整）；
    # 尽调场景另有场景级上限（scenarios/dd04/agents.yaml controller.max_total_tokens），优先于此值。
    run_max_tool_rounds: int | None = None
    run_timeout_seconds: float | None = None
    run_max_total_tokens: int = 1048576
    # 剩余时限不足该值时不再发起模型调用，直接以 run_timeout 结束
    run_min_llm_budget_seconds: float = 1.0

    # SSE 无新事件时的心跳间隔（秒），防止代理断开空闲连接
    sse_keepalive_seconds: float = 15.0

    # 样本数据版本：灌入种子时递增，evidence 据此标记数据快照版本
    data_version: int = 1
    csv_import_max_bytes: int = 10 * 1024 * 1024
    csv_import_max_rows: int = 20000

    # 会话历史传入模型的轮数上限（上下文管理起点）
    context_max_history_messages: int = 12
    # 更早的消息最多取多少条压缩为摘要（超出部分不再进入上下文）
    context_max_compressed_messages: int = 40
    # 历史（含工具摘要）的估算 token 预算，超出时把最旧的轮次压缩为摘要
    context_history_token_budget: int = 4000
    # 单个 run 的工具结果摘要字符上限
    context_tool_summary_chars: int = 1200

    database_url: str = "sqlite:///./ocft.db"

    # 前端构建产物目录（npm run build 生成）。目录存在时后端在 / 下直接提供页面，
    # 离线交付不需要 Node.js；相对路径以 ocft-backend/ 为基准
    frontend_dist_dir: str = "../ocft-starter/dist"

    @model_validator(mode="after")
    def _prefer_yaml_database(self) -> "Settings":
        """@why config.yaml 是统一配置来源：database 段配置了（url 或 host 非空）
        就优先于环境变量 / .env；未配置时保持原有行为。enc: 值已在 db.config 中解密。
        """
        from db.config import database_url_from_config

        url = database_url_from_config()
        if url:
            self.database_url = url
        return self

    def validate_runtime(self) -> None:
        """启动时校验：模型名必须精确匹配比赛指定值。"""
        if self.llm_model != REQUIRED_MODEL:
            raise RuntimeError(
                f"LLM_MODEL 配置为 {self.llm_model!r}，比赛规则要求运行时"
                f"只允许 {REQUIRED_MODEL!r}。请修正 .env 或环境变量。")
        if self.llm_api_model not in ALLOWED_API_MODELS:
            raise RuntimeError(
                f"LLM_API_MODEL 配置为 {self.llm_api_model!r}，只允许 "
                f"{sorted(ALLOWED_API_MODELS)}（同一模型 V4.1 Flash 的 API 名称），"
                "不得切换到其他模型。")

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_base_url)


settings = Settings()
