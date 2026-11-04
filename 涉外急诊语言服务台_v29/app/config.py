# -*- coding: utf-8 -*-
"""全局配置：全部从环境变量/.env 读取，禁止把密钥写进代码。"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "涉外急诊语言服务台"
    env: str = "dev"
    secret_key: str = "dev-only-change-me"
    access_token_minutes: int = 180
    cookie_secure: bool = False           # 生产必须 True（HTTPS）
    cookie_samesite: str = "lax"

    database_url: str = "sqlite:///./data/app.db"

    # 向量：local=本地哈希（离线、确定性）；bigmodel=智谱 embedding-3
    embedding_provider: str = "local"
    embedding_dim: int = 1024
    bigmodel_api_key: str = ""
    bigmodel_base: str = "https://open.bigmodel.cn/api/paas/v4"
    bigmodel_embedding_model: str = "embedding-3"

    # 生成：mock=不调用模型（只给检索摘录）；deepseek=DeepSeek；generic=任意兼容 OpenAI 的服务
    llm_provider: str = "mock"
    deepseek_api_key: str = ""
    deepseek_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    generic_base: str = ""
    generic_api_key: str = ""
    generic_model: str = ""

    # 翻译：mock=术语+句对拼接；deepseek；generic=任意 MT 端口（百度/腾讯/DeepL 等）
    mt_provider: str = "mymemory"   # mymemory=免费公共端口（演示可用）；deepseek；generic；mock
    generic_mt_url: str = ""
    generic_mt_key: str = ""
    generic_mt_method: str = "POST"
    generic_mt_payload_tpl: str = '{"q": "{text}", "source": "{src}", "target": "{tgt}"}'
    generic_mt_result_path: str = "trans_result.0.dst"
    mymemory_email: str = ""          # 可选：MyMemory 官方 de= 参数，可提高每日免费额度

    # 资讯中文化：llm 优先；无 LLM 时用免费公共 MT 端口（mymemory）兜底
    news_mt_provider: str = "mymemory"      # llm | mymemory | none
    news_mt_max_items: int = 60

    qa_top_k: int = 5
    refuse_threshold: float = 0.35       # 余弦低于此值直接拒答（语义向量 provider，如 bigmodel）
    refuse_threshold_local: float = 0.15 # local 哈希向量余弦普遍偏低（0.16–0.30），单独校准
    max_text_len: int = 5000   # 单次翻译最多 5000 字（前后端同时校验）

    # 语音识别（v=27）：mock=课程演示（不联网、显式 demo 标记）、http=服务端中转。
    # 密钥只在服务端；音频不落盘、不进日志。前端只连同源 /api/speech/recognize。
    asr_provider: str = "mock"
    asr_http_url: str = ""
    asr_http_key: str = ""
    asr_http_timeout: float = 20.0
    asr_max_audio_bytes: int = 8 * 1024 * 1024
    asr_max_duration_ms: int = 60000
    asr_rate_limit: int = 10
    asr_demo_text: str = ""
    asr_demo_text_en: str = ""

    # 登录限流（应用层兜底，生产还有 Nginx limit_req）
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    cors_origins: str = ""               # 逗号分隔；为空表示只允许同源


@lru_cache
def get_settings() -> Settings:
    return Settings()
