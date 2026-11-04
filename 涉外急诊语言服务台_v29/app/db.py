# -*- coding: utf-8 -*-
"""数据库：默认 SQLite（本地开发），生产用 PostgreSQL 15 + pgvector。"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  确保模型已注册

    if not _is_sqlite:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    if not _is_sqlite:
        # 生产：切片向量单独放 pgvector 表，便于建 HNSW 索引
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chunk_vectors (
                    chunk_id BIGINT PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                    embedding vector(1024) NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_chunk_vectors_hnsw
                ON chunk_vectors USING hnsw (embedding vector_cosine_ops)
            """))
