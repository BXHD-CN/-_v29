# -*- coding: utf-8 -*-
"""数据模型：用户、私有术语/语料、公开术语/语料、切片、资讯、审计。"""
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String,
                        Text, UniqueConstraint, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(64), default="")
    role: Mapped[str] = mapped_column(String(16), default="user")   # user / admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    terms: Mapped[list["UserTerm"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    corpus: Mapped[list["UserCorpus"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class PublicTerm(Base):
    """公共术语库（只读，来自 V1.3 总库 4,154 条）。"""
    __tablename__ = "public_terms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    zh: Mapped[str] = mapped_column(String(255), index=True)
    en: Mapped[str] = mapped_column(String(255), index=True)
    lang_pair: Mapped[str] = mapped_column(String(16), default="zh-en")
    domain: Mapped[str] = mapped_column(String(64), default="")
    subdomain: Mapped[str] = mapped_column(String(64), default="")
    abbreviation: Mapped[str] = mapped_column(String(64), default="")
    definition_zh: Mapped[str] = mapped_column(Text, default="")
    definition_en: Mapped[str] = mapped_column(Text, default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    audit_status: Mapped[str] = mapped_column(String(16), default="来源核验")
    samples: Mapped[int] = mapped_column(Integer, default=0)


class PublicCorpus(Base):
    """公共平行语料（只读，来自 V1.3 总库 8,308 句）。"""
    __tablename__ = "public_corpus"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    corpus_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    term_id: Mapped[str] = mapped_column(String(32), index=True, default="")
    zh: Mapped[str] = mapped_column(Text)
    en: Mapped[str] = mapped_column(Text)
    lang_pair: Mapped[str] = mapped_column(String(16), default="zh-en")
    register: Mapped[str] = mapped_column(String(16), default="")
    domain: Mapped[str] = mapped_column(String(64), default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    audit_status: Mapped[str] = mapped_column(String(16), default="来源核验")


class UserTerm(Base):
    """用户私有术语：只在自己的账户里可见、可编辑。"""
    __tablename__ = "user_terms"
    __table_args__ = (UniqueConstraint("user_id", "zh", "en", name="uq_user_term"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    zh: Mapped[str] = mapped_column(String(255))
    en: Mapped[str] = mapped_column(String(255), default="")
    lang_pair: Mapped[str] = mapped_column(String(16), default="zh-en")
    domain: Mapped[str] = mapped_column(String(64), default="")
    definition: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_public_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 从公共库复制而来
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    owner: Mapped[User] = relationship(back_populates="terms")


class UserCorpus(Base):
    """用户私有语料：同样只在自己账户内可见、可编辑。"""
    __tablename__ = "user_corpus"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    zh: Mapped[str] = mapped_column(Text)
    en: Mapped[str] = mapped_column(Text)
    lang_pair: Mapped[str] = mapped_column(String(16), default="zh-en")
    register: Mapped[str] = mapped_column(String(16), default="")
    term_id: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    source_url: Mapped[str] = mapped_column(String(512), default="")
    source_public_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    owner: Mapped[User] = relationship(back_populates="corpus")


class Chunk(Base):
    """知识库切片：300–500 字，带可追溯来源；embedding 由向量服务写入。"""
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    chunk_no: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(512), default="")
    section: Mapped[str] = mapped_column(String(255), default="")
    page: Mapped[str] = mapped_column(String(32), default="")
    lang: Mapped[str] = mapped_column(String(8), default="zh")
    license: Mapped[str] = mapped_column(String(255), default="")
    fetched_at: Mapped[str] = mapped_column(String(32), default="")
    doc_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[str] = mapped_column(Text, default="")   # SQLite: JSON；PG 用 chunk_vectors
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class NewsItem(Base):
    """外语信息聚合：爬虫抓取 + 中文化。"""
    __tablename__ = "news_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    title_en: Mapped[str] = mapped_column(String(512), default="")
    title_zh: Mapped[str] = mapped_column(String(512), default="")
    summary_en: Mapped[str] = mapped_column(Text, default="")
    summary_zh: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[str] = mapped_column(String(32), default="")
    fetched_at: Mapped[str] = mapped_column(String(32), default="")
    license: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(16), default="published")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str] = mapped_column(String(32), default="")
    object_id: Mapped[str] = mapped_column(String(64), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


Index("ix_chunks_doc", Chunk.doc_id)

class LocalTerm(Base):
    """东盟本地语对照（1,040 条，越/泰/印尼/马来各 260）。"""
    __tablename__ = "local_terms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    lang: Mapped[str] = mapped_column(String(16), index=True)
    lang_code: Mapped[str] = mapped_column(String(8), index=True)
    category: Mapped[str] = mapped_column(String(16), default="")
    domain: Mapped[str] = mapped_column(String(64), default="")
    scene: Mapped[str] = mapped_column(String(64), default="")
    zh: Mapped[str] = mapped_column(String(255), index=True)
    en: Mapped[str] = mapped_column(String(255), default="")
    local_text: Mapped[str] = mapped_column(String(512), default="")
    romanization: Mapped[str] = mapped_column(String(512), default="")
    pron_hint: Mapped[str] = mapped_column(String(255), default="")
    usage_note: Mapped[str] = mapped_column(Text, default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    audit_status: Mapped[str] = mapped_column(String(16), default="待母语审校")


class CultureExpr(Base):
    """东盟文化表达与禁忌表达（738 条，来自 V1.3「文化表达总表」）。

    与术语库的差别：术语库回答「这个医学概念怎么说」，本表回答「这话能不能说、
    怎么说才不失礼」，两者是同一场景的两种视角。
    """
    __tablename__ = "culture_exprs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expr_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    ctype: Mapped[str] = mapped_column(String(32), index=True, default="")
    subcategory: Mapped[str] = mapped_column(String(64), index=True, default="")
    country: Mapped[str] = mapped_column(String(32), index=True, default="")
    original: Mapped[str] = mapped_column(String(255), index=True)
    original_lang: Mapped[str] = mapped_column(String(32), default="")
    literal_zh: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[str] = mapped_column(Text, default="")
    rec_en: Mapped[str] = mapped_column(String(512), default="")
    rec_zh: Mapped[str] = mapped_column(String(255), default="")
    scene: Mapped[str] = mapped_column(String(64), index=True, default="")
    taboo_level: Mapped[str] = mapped_column(String(8), index=True, default="无")
    usage_note: Mapped[str] = mapped_column(Text, default="")
    example_zh: Mapped[str] = mapped_column(Text, default="")
    example_en: Mapped[str] = mapped_column(Text, default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")


class EnglishVariant(Base):
    """东盟英语变体整句改写（150 条，来自 V1.3「英语变体转写」）。

    把 Singlish / Manglish 等变体整句还原为标准英语，并给出医疗场景改写。
    """
    __tablename__ = "english_variants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    variant_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    variant: Mapped[str] = mapped_column(String(32), index=True, default="")
    country: Mapped[str] = mapped_column(String(32), index=True, default="")
    original: Mapped[str] = mapped_column(Text)
    features: Mapped[str] = mapped_column(Text, default="")
    literal_zh: Mapped[str] = mapped_column(Text, default="")
    standard_en: Mapped[str] = mapped_column(Text, default="")
    medical_en: Mapped[str] = mapped_column(Text, default="")
    register_note: Mapped[str] = mapped_column(Text, default="")
    meaning_zh: Mapped[str] = mapped_column(Text, default="")
    source_code: Mapped[str] = mapped_column(String(64), default="")


class SourceRef(Base):
    """来源清单（69 个编号）：术语/语料的来源可核查入口。"""
    __tablename__ = "sources"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    org: Mapped[str] = mapped_column(String(255), default="")
    level: Mapped[str] = mapped_column(String(8), default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    applies: Mapped[str] = mapped_column(String(255), default="")


class CorpusVector(Base):
    """平行语料句级向量（float32 二进制，1024 维）。"""
    __tablename__ = "corpus_vectors"
    corpus_id: Mapped[int] = mapped_column(ForeignKey("public_corpus.id", ondelete="CASCADE"), primary_key=True)
    vector: Mapped[bytes] = mapped_column(LargeBinary)

class TranslationHistory(Base):
    """翻译历史：每人独立保存，侧栏可回看，不覆盖当前输入。"""
    __tablename__ = "translation_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    src: Mapped[str] = mapped_column(String(8), default="zh")
    tgt: Mapped[str] = mapped_column(String(8), default="en")
    source_text: Mapped[str] = mapped_column(Text)
    translation: Mapped[str] = mapped_column(Text, default="")
    chars: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
