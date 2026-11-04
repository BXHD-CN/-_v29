# -*- coding: utf-8 -*-
"""task-10 自测脚本：mymemory MT 接驳 + local_terms 本地语术语锁定（8 个方向）。

运行：cd work/site && ./.venv/Scripts/python.exe docs/selftest_mt.py
说明：8 个方向之间固定间隔 2s（MyMemory 公共端口的 QPS 很低，连续请求必被 429）；
      成功路径另用 monkeypatch 单元验证（不联网），避免把公共端口额度耗在测试上。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.main import app
from app.db import SessionLocal
from app.models import AuditLog, User
from app.services import translate_service as ts

ZH_SENT = "预检分诊：请先在分诊台登记，分诊护士会按分诊标准安排就诊。"
REVERSE = {
    "en": "Please wait at the triage desk; the triage nurse will call you.",
    "vi": "Vui lòng chờ tại quầy phân loại, điều dưỡng phân loại sẽ gọi bạn.",
    "th": "กรุณารอที่จุดคัดแยกผู้ป่วย พยาบาลคัดแยกผู้ป่วยจะเรียกคุณ",
}
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("[PASS] " if ok else "[FAIL] ") + name + (" | " + detail if detail else ""))


def post(client, url, payload, csrf):
    return client.post(url, json=payload, headers={"X-CSRF-Token": csrf})


suffix = str(int(time.time()))[-6:]
user = {"email": f"mt_selftest_{suffix}@example.com", "username": f"mt_selftest_{suffix}",
        "password": "MtTest#2026", "display_name": "MT 自测"}

with TestClient(app) as client:
    r = client.post("/api/auth/register", json=user)
    assert r.status_code == 201, r.text
    csrf = client.post("/api/auth/login",
                       json={"account": user["username"], "password": user["password"]}
                       ).json()["csrf_token"]

    ts.cache_clear()

    langs = client.get("/api/translate/languages").json()
    check("providers.mt = mymemory", langs["providers"]["mt"] == "mymemory",
          json.dumps(langs["providers"]))

    # MyMemory 单请求探测（独立于应用冷却，用于判断当前网络是否可用）
    import httpx
    try:
        with httpx.Client(timeout=8.0) as probe:
            resp = probe.get("https://api.mymemory.translated.net/get",
                             params={"q": "预检分诊", "langpair": "zh-CN|vi"},
                             headers={"User-Agent": "AIT-CourseBot/1.0 (+ait-course-demo)"})
        payload = resp.json()
        print(f"[MyMemory 单请求探测] HTTP {resp.status_code} | responseStatus="
              f"{payload.get('responseStatus')} | {str(payload.get('responseDetails'))[:120]}")
    except Exception as exc:
        print(f"[MyMemory 单请求探测] 网络异常：{type(exc).__name__}")
    check("local_terms 各语 260 条",
          all(len(ts._local_term_index(c)) == 260 for c in ("vi", "th", "id", "ms")),
          str({c: len(ts._local_term_index(c)) for c in ("vi", "th", "id", "ms")}))

    print("\n=== 8 个翻译方向（HTTP 实测）===")
    directions = [("zh", "en", ZH_SENT), ("zh", "vi", ZH_SENT), ("zh", "th", ZH_SENT),
                  ("zh", "id", ZH_SENT), ("zh", "ms", ZH_SENT)]
    directions += [(src, "zh", text) for src, text in REVERSE.items()]
    for index, (src, tgt, text) in enumerate(directions):
        if index:
            time.sleep(2.0)   # Lead 要求：每个方向间隔 2s
        r = post(client, "/api/translate", {"text": text, "src": src, "tgt": tgt}, csrf)
        body = r.json()
        ok = r.status_code == 200 and body["provider"] in ("mymemory", "mock")
        detail = f"status={r.status_code} provider={body.get('provider')} degraded={body.get('degraded')}"
        if tgt in ts.LOCAL_TARGETS:
            locked = body.get("locked_terms") or []
            all_lang = all(t.get("lang") == tgt for t in locked)
            must_use_ok = all(t.get("must_use") == t.get("local_text") for t in locked)
            hit = any(t["local_text"] in body["translation"] for t in locked) if locked else False
            ok = ok and bool(locked) and all_lang and must_use_ok and hit
            detail += f" locked={len(locked)} lang_ok={all_lang} local_text_in_translation={hit}"
        elif tgt == "en":
            ok = ok and any(t.get("en") for t in body.get("locked_terms") or [])
            detail += f" locked={len(body.get('locked_terms') or [])}"
        if src == "zh" and tgt == "en":   # 语料上下文必须来自向量检索并带 score
            ctx = body.get("context_pairs") or []
            check("context_pairs 带 score（语料向量检索）",
                  bool(ctx) and all("score" in item for item in ctx)
                  and any(item["score"] > 0 for item in ctx),
                  "scores=" + str([item.get("score") for item in ctx]))
        if src == "zh" and tgt == "vi":   # Lead 点名核对：must_use 必须是 local_terms.local_text
            must = {t["zh"]: t["must_use"] for t in body.get("locked_terms") or []}
            check("zh->vi must_use 取 local_terms.local_text",
                  must.get("预检分诊") == "phân loại sàng lọc",
                  f"预检分诊 -> {must.get('预检分诊')}")
        check(f"{src}->{tgt}", ok, detail + f" | {body['translation'][:56]}")
        print(f"    translation: {body['translation'][:100]}")
        print(f"    notes: {body['notes']}")

    # ---- 进程内 LRU 缓存 ----
    print("\n=== 进程内 LRU 缓存 ===")
    sample = "缓存验证：请先在分诊台登记。"
    r1 = ts.translate(sample, "zh", "vi")
    r2 = ts.translate(sample, "zh", "vi")
    check("同 text+src+tgt 命中缓存且结果一致",
          r1 == r2 and len(ts._TRANSLATE_CACHE) <= ts._TRANSLATE_CACHE_MAX,
          f"cache_size={len(ts._TRANSLATE_CACHE)} capacity={ts._TRANSLATE_CACHE_MAX}")

    # ---- 单元级：MyMemory 响应解析 ----
    print("\n=== 单元级：_parse_mymemory ===")
    good = ts._parse_mymemory({"responseStatus": 200,
                               "responseData": {"translatedText": "phân loại &amp; sàng lọc"}})
    check("解析正常响应（含 HTML 实体反转义）", good == "phân loại & sàng lọc", good)
    bad_cases = [
        {"responseStatus": 429, "responseData": {"translatedText": "MYMEMORY WARNING: QUOTA"}},
        {"responseStatus": 200, "responseData": {"translatedText": ""}},
        {"responseStatus": 403, "responseData": {}},
    ]
    ok_bad = True
    for payload in bad_cases:
        try:
            ts._parse_mymemory(payload)
            ok_bad = False
        except ts.MTUnavailable:
            pass
    check("限额/空结果/非 200 都抛 MTUnavailable", ok_bad)

    # ---- 单元级：模拟 MyMemory 成功（不联网），验证 provider 与译后校验 ----
    print("\n=== 单元级：模拟 MyMemory 成功路径 ===")
    original = ts._mymemory_translate

    def fake_translate(text: str, src: str, tgt: str) -> str:
        # 故意只翻部分内容且不含本地语术语，用来验证译后校验会强替
        return text.replace("。", ". ")

    ts._mymemory_translate = fake_translate
    try:
        r = ts.translate("预检分诊：请先在分诊台登记。", "zh", "vi")
        check("成功路径 provider=mymemory / degraded=false",
              r["provider"] == "mymemory" and r["degraded"] is False,
              f"provider={r['provider']} degraded={r['degraded']}")
        fixed = [n for n in r["notes"] if n.startswith("term_fixed:")]
        hit = all(t["local_text"] in r["translation"] for t in r["locked_terms"])
        check("译后校验强替缺失本地语术语并写 note", bool(fixed) and hit,
              f"notes={fixed} translation={r['translation'][:70]}")
        r_en = ts.translate("预检分诊：请先在分诊台登记。", "zh", "en")
        check("成功路径 zh->en 仍按 en 译法校验",
              r_en["provider"] == "mymemory" and r_en["degraded"] is False
              and all(t["en"] in r_en["translation"] for t in r_en["locked_terms"]),
              r_en["translation"][:70])
    finally:
        ts._mymemory_translate = original

    # ---- 清理测试账号 ----
    with SessionLocal() as db:
        ids = [u.id for u in db.scalars(
            select(User).where(User.username == user["username"])).all()]
        db.execute(delete(AuditLog).where(AuditLog.user_id.in_(ids)))
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()
    print(f"\ncleaned test user: {ids}")

failed = [name for name, ok in results if not ok]
print(f"\n==== 结果：{len(results) - len(failed)}/{len(results)} 通过 ====")
sys.exit(1 if failed else 0)
