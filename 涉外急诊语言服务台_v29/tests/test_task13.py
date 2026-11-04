# -*- coding: utf-8 -*-
"""task-13 增测：逐句对照 segments、翻译历史、私有库 Excel/JSON 导入导出、CSRF/登录强制。"""
import io
import json
import os
import tempfile

# 单独运行本文件时也要用独立测试库；全套跑时 test_api.py 已设置 DATABASE_URL
if not os.environ.get("DATABASE_URL"):
    _TEST_DB = os.path.join(tempfile.gettempdir(), "ait_task13.db")
    if os.path.exists(_TEST_DB):
        os.remove(_TEST_DB)
    os.environ["DATABASE_URL"] = "sqlite:///" + _TEST_DB
os.environ.setdefault("SECRET_KEY", "test-secret-key-which-is-long-enough-32")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import PublicTerm  # noqa: E402

PASSWORD = "Passw0rd!x"


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def login(client, name: str) -> str:
    client.post("/api/auth/register", json={
        "email": f"{name}@example.com", "username": name,
        "password": PASSWORD, "display_name": name})
    r = client.post("/api/auth/login", json={"account": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def headers(csrf: str) -> dict:
    return {"X-CSRF-Token": csrf}


def seed_term() -> None:
    db = SessionLocal()
    try:
        exists = db.query(PublicTerm).filter(PublicTerm.term_id == "T-T13-1").first()
        if not exists:
            db.add(PublicTerm(term_id="T-T13-1", zh="预检分诊", en="triage",
                              domain="分诊与接诊", source_code="T03", audit_status="来源核验"))
            db.commit()
    finally:
        db.close()


def test_translate_returns_segments_and_saves_history(client):
    seed_term()
    csrf = login(client, "t13a")
    text = "预检分诊：请先在分诊台登记。患者出现胸痛时应立即做心电图。"
    r = client.post("/api/translate", json={"text": text, "src": "zh", "tgt": "en"},
                    headers=headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("segments"), list) and len(body["segments"]) >= 2
    for segment in body["segments"]:
        assert {"src", "tgt", "terms", "pairs"} <= set(segment)
        assert segment["src"] and isinstance(segment["terms"], list)
        assert isinstance(segment["pairs"], list)
    # 首句包含“预检分诊”，应带上锁定术语
    assert any(segment["terms"] for segment in body["segments"])
    assert body["history_id"]

    history = client.get("/api/me/translations?limit=10").json()
    assert history["total"] >= 1
    item = next(row for row in history["items"] if row["id"] == body["history_id"])
    assert item["source_text"] == text
    assert item["translation"] == body["translation"]
    assert item["chars"] == len(text)
    assert item["src"] == "zh" and item["tgt"] == "en"
    assert item["provider"] == body["provider"]


def test_history_is_per_user_and_deletable(client):
    csrf_a = login(client, "t13a")
    body = client.post("/api/translate", json={"text": "分诊台在哪里？", "src": "zh", "tgt": "en"},
                       headers=headers(csrf_a)).json()
    hid = body["history_id"]
    assert hid
    # 切到 b（登录会替换 cookie 与 csrf），b 看不到 a 的历史，也不能删
    csrf_b = login(client, "t13b")
    assert client.get("/api/me/translations").json()["total"] == 0
    assert client.delete(f"/api/me/translations/{hid}", headers=headers(csrf_b)).status_code == 404
    # 切回 a，自己可以删
    csrf_a = login(client, "t13a")
    assert client.delete(f"/api/me/translations/{hid}", headers=headers(csrf_a)).status_code == 200
    remaining = [row["id"] for row in client.get("/api/me/translations?limit=100").json()["items"]]
    assert hid not in remaining
    assert client.delete(f"/api/me/translations/{hid}", headers=headers(csrf_a)).status_code == 404


def test_translate_rejects_over_5000_chars(client):
    csrf = login(client, "t13a")
    r = client.post("/api/translate", json={"text": "字" * 5001, "src": "zh", "tgt": "en"},
                    headers=headers(csrf))
    assert r.status_code in (400, 422)


def test_export_terms_xlsx_and_json(client):
    csrf = login(client, "t13a")
    for name in ("导出甲", "导出乙"):
        client.post("/api/me/terms", json={"zh": name, "en": f"export-{name}"},
                    headers=headers(csrf))
    total = client.get("/api/me/terms?page_size=100").json()["total"]

    r = client.get("/api/me/terms/export.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    wb = load_workbook(io.BytesIO(r.content), read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    assert rows[0][:3] == ("zh", "en", "lang_pair")
    assert len(rows) - 1 == total

    r = client.get("/api/me/terms/export.xlsx?format=json")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == total
    assert {"zh", "en", "lang_pair", "definition"} <= set(data[0])


def test_import_terms_json_and_xlsx(client):
    csrf = login(client, "t13a")
    before = client.get("/api/me/terms?page_size=100").json()["total"]

    payload = [
        {"zh": "导入甲", "en": "import-a", "domain": "分诊与接诊"},
        {"zh": "导入甲", "en": "import-a"},          # 文件内重复 -> skipped
        {"zh": "", "en": "no-zh"},                    # 缺 zh -> skipped
    ]
    r = client.post("/api/me/terms/import",
                    files={"file": ("import.json", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                    "application/json")},
                    headers=headers(csrf))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1 and body["skipped"] == 2
    assert body["errors"] and body["errors"][0]["reason"] == "zh 为空"

    wb = Workbook()
    ws = wb.active
    ws.append(["zh", "en", "lang_pair", "domain", "definition", "note", "source_code", "source_url"])
    ws.append(["导入乙", "import-b", "zh-en", "分诊与接诊", "释义", "备注", "T01", "https://example.com"])
    buffer = io.BytesIO()
    wb.save(buffer)
    r = client.post("/api/me/terms/import",
                    files={"file": ("import.xlsx", buffer.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                    headers=headers(csrf))
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1

    after = client.get("/api/me/terms?page_size=100").json()
    assert after["total"] == before + 2
    imported = {row["zh"] for row in after["items"]}
    assert {"导入甲", "导入乙"} <= imported


def test_import_export_corpus(client):
    csrf = login(client, "t13a")
    payload = [{"zh": "请先在分诊台登记。", "en": "Please register at the triage desk first."},
               {"zh": "请先在分诊台登记。", "en": "Please register at the triage desk first."}]
    r = client.post("/api/me/corpus/import",
                    files={"file": ("corpus.json", json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                    "application/json")},
                    headers=headers(csrf))
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1 and r.json()["skipped"] == 1

    r = client.get("/api/me/corpus/export.xlsx?format=json")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 1
    assert {"zh", "en", "register"} <= set(rows[0])


def test_sentence_align_model_path_and_fallback(monkeypatch):
    from app.services import sentence_align, llm

    # 1) 模拟 DeepSeek 返回合法 JSON 数组 -> 逐句译文严格对齐
    monkeypatch.setattr(llm, "is_mock", lambda: False)
    monkeypatch.setattr(llm, "chat", lambda messages, **kwargs: '["A sentence.","B sentence."]')
    segs = sentence_align.build_segments(
        "第一句。第二句。", "zh", "en",
        result={"translation": "", "locked_terms": [], "context_pairs": []})
    assert [seg["tgt"] for seg in segs] == ["A sentence.", "B sentence."]
    assert [seg["src"] for seg in segs] == ["第一句。", "第二句。"]

    # 2) 模型输出不是 JSON -> 降级为整段译文按句切分
    monkeypatch.setattr(llm, "chat", lambda messages, **kwargs: "not a json array")
    segs = sentence_align.build_segments(
        "第一句。第二句。", "zh", "en",
        result={"translation": "X one. Y two.", "locked_terms": [], "context_pairs": []})
    assert [seg["tgt"] for seg in segs] == ["X one.", "Y two."]


def test_sentence_align_terms_and_pairs_mapping():
    from app.services import sentence_align

    result = {
        "translation": "预检分诊在分诊台。患者胸痛。",
        "locked_terms": [{"term_id": "T1", "zh": "预检分诊", "en": "triage",
                          "matched": "预检分诊", "must_use": "triage"}],
        "context_pairs": [{"corpus_id": "C1", "zh": "预检分诊台在第一诊区。",
                           "en": "The triage desk is in zone one.", "score": 0.8}],
    }
    segs = sentence_align.build_segments("预检分诊在分诊台。患者胸痛。", "zh", "en", result=result)
    assert len(segs) == 2
    assert segs[0]["terms"] and segs[0]["terms"][0]["must_use"] == "triage"
    assert segs[0]["pairs"] and segs[0]["pairs"][0]["corpus_id"] == "C1"
    assert segs[1]["terms"] == [] and segs[1]["pairs"] == []


def test_new_endpoints_require_csrf_and_login(client):
    csrf = login(client, "t13a")
    # 无 CSRF 的写请求 -> 403
    r = client.post("/api/me/terms/import",
                    files={"file": ("x.json", b"[]", "application/json")})
    assert r.status_code == 403
    assert client.delete("/api/me/translations/1").status_code == 403
    # 未登录 -> 401
    with TestClient(app) as anon:
        assert anon.get("/api/me/translations").status_code == 401
        assert anon.get("/api/me/terms/export.xlsx").status_code == 401
        assert anon.post("/api/translate", json={"text": "x", "src": "zh", "tgt": "en"}).status_code == 401
