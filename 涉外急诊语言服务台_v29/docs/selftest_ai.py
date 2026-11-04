# -*- coding: utf-8 -*-
"""ai-core 自测脚本：真实启动 FastAPI 应用（TestClient），覆盖翻译、RAG、限流、降级。"""
import json
import os
import sys
import time

# 以 work/site 为项目根，保证 app 包可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.main import app
from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, Chunk, User
from app.services import rag
from app.services.embedding import EmbeddingUnavailable, embed_texts

settings = get_settings()
suffix = str(int(time.time()))[-6:]
USER = {"email": f"ai_selftest_{suffix}@example.com",
        "username": f"ai_selftest_{suffix}",
        "password": "Selftest#2026",
        "display_name": "AI 自测"}

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("[PASS] " if ok else "[FAIL] ") + name + (" | " + detail if detail else ""))


def post_json(client, url, payload, csrf):
    return client.post(url, json=payload, headers={"X-CSRF-Token": csrf})


def register_login(client):
    r = client.post("/api/auth/register", json=USER)
    assert r.status_code == 201, r.text
    r = client.post("/api/auth/login", json={"account": USER["username"], "password": USER["password"]})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


with TestClient(app) as client:
    csrf = register_login(client)

    # ---------- 0. health / providers ----------
    health = client.get("/api/health").json()
    check("GET /api/health", health.get("status") == "ok", json.dumps(health["counts"], ensure_ascii=False))
    # MT_PROVIDER 由 Lead 在 .env 配置（mock 或 mymemory），这里只校验 provider 合法
    check("providers 合法（embedding=local / llm=mock / mt 已配置）",
          health["providers"]["llm"] == "mock"
          and health["providers"]["embedding"] == "local"
          and health["providers"]["mt"] in ("mock", "mymemory", "deepseek", "generic"),
          json.dumps(health["providers"]))

    # ---------- 1. 语种列表 ----------
    langs = client.get("/api/translate/languages")
    check("GET /api/translate/languages", langs.status_code == 200
          and len(langs.json()["languages"]) == 6, json.dumps(langs.json()["providers"], ensure_ascii=False))

    # ---------- 2. 翻译：术语锁定 ----------
    text = "预检分诊：请先在分诊台登记，分诊护士会按分诊标准安排就诊。"
    r = post_json(client, "/api/translate", {"text": text, "src": "zh", "tgt": "en"}, csrf)
    body = r.json()
    check("POST /api/translate 200", r.status_code == 200, f"status={r.status_code}")
    locked_zh = {item["zh"] for item in body.get("locked_terms", [])}
    check("术语锁定命中中文术语", {"预检分诊", "分诊台", "分诊护士", "分诊标准"} <= locked_zh,
          f"locked={sorted(locked_zh)}")
    check("译文含锁定术语译法", all(item["en"].lower() in body["translation"].lower()
                                     for item in body["locked_terms"] if item["en"]),
          "translation=" + body["translation"][:80])
    # MT_PROVIDER 由 .env 决定：mock（无 Key 演示）/ mymemory（公共端口）/ deepseek。
    # 配置了真实 MT 时不要求 degraded=true，只校验返回结构完整。
    check("翻译返回 provider / notes / context_pairs / request_id 结构完整",
          body["provider"] in ("mock", "mymemory", "deepseek", "generic")
          and isinstance(body["notes"], list)
          and isinstance(body["context_pairs"], list) and body["request_id"] != "",
          f"provider={body['provider']} degraded={body['degraded']} notes={body['notes']}")

    # ---------- 3. 翻译：英文术语命中 + 反向 ----------
    r = post_json(client, "/api/translate",
                  {"text": "Please wait at the triage desk; the triage nurse will call you.", "src": "en", "tgt": "zh"}, csrf)
    body_en = r.json()
    locked_en = {item["matched"].lower() for item in body_en.get("locked_terms", [])}
    check("英文术语锁定（triage desk / triage nurse）",
          any("triage" in x for x in locked_en), f"matched={sorted(locked_en)}")
    check("en->zh 译文含中文术语", "分诊" in body_en["translation"], body_en["translation"][:60])

    # ---------- 3b. 5 语方向（无术语/语料时给演示译文，不报错） ----------
    r = post_json(client, "/api/translate", {"text": "预检分诊", "src": "zh", "tgt": "vi"}, csrf)
    check("zh->vi 演示模式返回 200", r.status_code == 200
          and bool(r.json().get("translation")), r.json().get("translation", "")[:40])

    # ---------- 4. 翻译：参数校验 ----------
    check("同语种方向 400", post_json(client, "/api/translate",
          {"text": "测试", "src": "zh", "tgt": "zh"}, csrf).status_code == 400)
    check("不支持语种 400", post_json(client, "/api/translate",
          {"text": "测试", "src": "zh", "tgt": "de"}, csrf).status_code == 400)
    check("缺 CSRF 403", client.post("/api/translate",
          json={"text": "测试", "src": "zh", "tgt": "en"}).status_code == 403)

    # ---------- 5. MT 降级：配置 deepseek 但无 Key ----------
    old_mt = settings.mt_provider
    settings.mt_provider = "deepseek"
    r = post_json(client, "/api/translate", {"text": "预检分诊流程", "src": "zh", "tgt": "en"}, csrf)
    deg = r.json()
    settings.mt_provider = old_mt
    check("MT 无 Key 时降级不 500", r.status_code == 200 and deg["degraded"] is True
          and deg["provider"] == "mock"
          and any(n.startswith("mt_degraded:") for n in deg["notes"]),
          f"status={r.status_code} notes={deg['notes']}")

    # ---------- 6. bigmodel 无 Key -> TypedException ----------
    old_emb = settings.embedding_provider
    settings.embedding_provider = "bigmodel"
    try:
        embed_texts(["测试"])
        raised = "none"
    except EmbeddingUnavailable as exc:
        raised = "EmbeddingUnavailable"
    finally:
        settings.embedding_provider = old_emb
    check("bigmodel 无 Key 抛 EmbeddingUnavailable", raised == "EmbeddingUnavailable", raised)

    # ---------- 7. QA：数据感知（chunks 可能已被 data-pipeline 灌入） ----------
    chunk_total = health["counts"]["chunks"]
    r = post_json(client, "/api/qa", {"question": "预检分诊的英文怎么表达？"}, csrf)
    qa_body = r.json()
    if chunk_total == 0:
        check("POST /api/qa（空库）按契约拒答", r.status_code == 200 and qa_body["refused"] is True
              and qa_body["reason"] in ("no_relevant_chunk", "embedding_unavailable"),
              f"reason={qa_body['reason']} mode={qa_body.get('mode')}")
    else:
        check(f"POST /api/qa 返回结构合法（库内已有 {chunk_total} 切片）",
              r.status_code == 200 and isinstance(qa_body.get("refused"), bool)
              and isinstance(qa_body.get("citations"), list)
              and qa_body.get("reason") in ("", "no_relevant_chunk")
              and isinstance(qa_body.get("elapsed_ms"), int),
              f"refused={qa_body['refused']} reason={qa_body['reason']} "
              f"mode={qa_body.get('mode')} n={len(qa_body.get('citations', []))}")
        # Lead 联调口径：local 向量单独阈值（0.15）后，库内问题要能命中 2–5 条引用
        in1 = post_json(client, "/api/qa", {"question": "传染病防治法规定了什么？"}, csrf).json()
        check("库内问题不拒答且有 2–5 条 citation",
              in1["refused"] is False and 2 <= len(in1["citations"]) <= 5,
              f"refused={in1['refused']} n={len(in1['citations'])} "
              f"top={in1['citations'][0]['score'] if in1['citations'] else '-'}")
        in2 = post_json(client, "/api/qa", {"question": "预检分诊是什么？"}, csrf).json()
        check("短句库内问题也不拒答", in2["refused"] is False and len(in2["citations"]) >= 2,
              f"refused={in2['refused']} n={len(in2['citations'])}")
        # 4 句回归（hybrid = 0.6*cos + 0.4*lex；阈值见 rag.HYBRID_REFUSE_THRESHOLD / rag.LEX_REFUSE_THRESHOLD）
        regression = [
            ("传染病防治法规定了什么？", False),
            ("预检分诊是什么？", False),
            ("今天美元汇率多少？", True),
            ("明天天气怎么样？", True),
        ]
        for question, should_refuse in regression:
            result = post_json(client, "/api/qa", {"question": question}, csrf).json()
            ok = (result["refused"] is should_refuse
                  and (not should_refuse or result["citations"] == [])
                  and (should_refuse or len(result["citations"]) >= 2))
            check(f"回归：{question} -> {'拒答' if should_refuse else '有引用'}", ok,
                  f"refused={result['refused']} n={len(result['citations'])}")
        check("hybrid 混合排序参数合法（权重 0.6/0.4，拒答阈值非负）",
              (rag.HYBRID_COS_WEIGHT, rag.HYBRID_LEX_WEIGHT) == (0.6, 0.4)
              and 0 < rag.HYBRID_REFUSE_THRESHOLD < rag.LEX_REFUSE_THRESHOLD < 1,
              f"{rag.HYBRID_COS_WEIGHT}/{rag.HYBRID_LEX_WEIGHT} "
              f"{rag.HYBRID_REFUSE_THRESHOLD}/{rag.LEX_REFUSE_THRESHOLD}")
        # qa/examples 的 4 条医疗相关库内题都要与当前数据一致；
        # 非医疗的库外演示题已按需求删除，拒答能力由上方 regression 独立校验。
        example_ok = True
        example_detail = []
        for item in client.get("/api/qa/examples").json()["examples"]:
            got = post_json(client, "/api/qa", {"question": item["question"]}, csrf).json()
            match = got["refused"] is (not item["in_scope"])
            example_ok = example_ok and match
            example_detail.append(f"{item['id']}:{'OK' if match else 'MISMATCH'}")
        check("4 条示例问题拒答/回答与 in_scope 一致", example_ok, " ".join(example_detail))

        # v=26：中文 bigram 对纯英文问题会虚高假重合，必须统一拒答且不带引用。
        en_out_of_scope = [
            "Recommend the best hotpot restaurant in Beijing.",
            "What is today's USD/CNY exchange rate?",
            "Who won the World Cup final?",
            "What is the weather like tomorrow?",
        ]
        en_ok = True
        en_detail = []
        for question in en_out_of_scope:
            got = post_json(client, "/api/qa", {"question": question}, csrf).json()
            passed = got["refused"] is True and got["citations"] == []
            en_ok = en_ok and passed
            en_detail.append(("OK" if passed else "LEAK") + ":" + question[:20])
        check("英文库外问题统一拒答且无引用", en_ok, " | ".join(en_detail))

        # 英文界面照抄预设题时映射回规范中文，不能被误判为库外。
        en_preset = client.get("/api/qa/examples?lang=en").json()["examples"][0]
        got_preset = post_json(client, "/api/qa", {"question": en_preset["question"]}, csrf).json()
        check("英文预设题映射回中文后不误拒",
              got_preset["refused"] is False and len(got_preset["citations"]) >= 1,
              f"refused={got_preset['refused']} n={len(got_preset['citations'])}")
    examples = client.get("/api/qa/examples").json()["examples"]
    check("GET /api/qa/examples 4 条全部为医疗相关库内题", len(examples) == 4
          and all(e["in_scope"] for e in examples))

    # ---------- 8. QA：临时灌 2 条切片 -> 摘录模式 + citations ----------
    seed_texts = [
        ("自检文档-分诊", "预检分诊是急诊接诊的第一环节。分诊护士依据分诊标准，在分诊台为患者测量生命体征，"
         "并按病情轻重安排就诊顺序。预检分诊记录需写入分诊记录单，作为后续诊疗与医疗文书的依据。"),
        ("自检文档-知情同意", "向外国患者解释手术知情同意时，应使用患者能理解的语言，说明手术目的、风险、"
         "替代方案与不手术的后果，并由具备资质的医师完成沟通。必要时通过专业医疗翻译协助，"
         "翻译人员不得代替医师作出医学判断。"),
    ]
    with SessionLocal() as db:
        for i, (title, txt) in enumerate(seed_texts):
            db.add(Chunk(doc_id=f"selftest-{suffix}", chunk_no=i, title=title, text=txt,
                         source_url="https://example.org/selftest", section="自检", page="",
                         lang="zh", license="selftest", embedding=json.dumps(embed_texts([txt])[0])))
        db.commit()
    try:
        r = post_json(client, "/api/qa", {"question": "预检分诊的分诊护士按什么标准安排就诊顺序？"}, csrf)
        seeded = r.json()
        check("有切片时 QA 不拒答", r.status_code == 200 and seeded["refused"] is False,
              f"refused={seeded['refused']} reason={seeded['reason']}")
        check("citations 结构完整（index/chunk_id/snippet<=120）",
              len(seeded["citations"]) >= 1
              and all(set(("index", "chunk_id", "title", "section", "page", "source_url",
                           "score", "snippet")) <= set(c) for c in seeded["citations"])
              and all(len(c["snippet"]) <= 120 for c in seeded["citations"]),
              f"n={len(seeded['citations'])} top={seeded['citations'][0]['score'] if seeded['citations'] else '-'}")
        check("无生成模型走摘录模式且带前缀", seeded["mode"] == "excerpt"
              and seeded["answer"].startswith(rag.EXCERPT_PREFIX), seeded["answer"][:40])

        # ---------- 8b. LLM 配了 deepseek 但无 Key -> 摘录模式，不 500 ----------
        old_llm = settings.llm_provider
        settings.llm_provider = "deepseek"
        try:
            r = post_json(client, "/api/qa", {"question": "预检分诊的分诊护士按什么标准安排就诊顺序？"}, csrf)
            degrade = r.json()
            check("LLM provider 不可用时降级摘录不 500",
                  r.status_code == 200 and degrade["refused"] is False
                  and degrade["mode"] == "excerpt"
                  and degrade["answer"].startswith(rag.EXCERPT_PREFIX),
                  f"status={r.status_code} mode={degrade.get('mode')}")
        finally:
            settings.llm_provider = old_llm

        # ---------- 9. 引用校验：伪造 LLM 输出 ----------
        old_is_mock = rag.llm.is_mock
        old_chat = rag.llm.chat
        try:
            rag.llm.is_mock = lambda: False
            bad_calls = {"n": 0}

            def bad_chat(messages, temperature=0.2, max_tokens=800, **kw):
                bad_calls["n"] += 1
                return "分诊护士按分诊标准安排就诊顺序。"   # 无 [n] 引用

            rag.llm.chat = bad_chat
            bad = rag.answer("预检分诊的分诊护士按什么标准安排就诊顺序？")
            check("引用校验失败重试 1 次后降级摘录",
                  bad_calls["n"] == 2 and bad["mode"] == "excerpt" and bad["citations"],
                  f"chat_calls={bad_calls['n']} mode={bad['mode']}")

            good_calls = {"n": 0}

            def good_chat(messages, temperature=0.2, max_tokens=800, **kw):
                good_calls["n"] += 1
                return "分诊护士依据分诊标准在分诊台为患者测量生命体征[1]，并按病情轻重安排就诊顺序[1]。"

            rag.llm.chat = good_chat
            good = rag.answer("预检分诊的分诊护士按什么标准安排就诊顺序？")
            check("引用合法时直接采用 LLM 答案",
                  good_calls["n"] == 1 and good["mode"] == "llm" and good["refused"] is False,
                  f"chat_calls={good_calls['n']} mode={good['mode']}")

            def out_of_range_chat(messages, temperature=0.2, max_tokens=800, **kw):
                return "分诊护士依据分诊标准安排就诊顺序[9]。"

            rag.llm.chat = out_of_range_chat
            oor = rag.answer("预检分诊的分诊护士按什么标准安排就诊顺序？")
            check("越界引用 [9] 视为无效 -> 摘录", oor["mode"] == "excerpt",
                  f"mode={oor['mode']} answer={oor['answer'][:30]}")
        finally:
            rag.llm.is_mock = old_is_mock
            rag.llm.chat = old_chat
    finally:
        with SessionLocal() as db:
            db.execute(delete(Chunk).where(Chunk.doc_id == f"selftest-{suffix}"))
            db.commit()

    # ---------- 10. 限流 ----------
    user2 = {"email": f"ai_selftest2_{suffix}@example.com", "username": f"ai_selftest2_{suffix}",
             "password": "Selftest#2026", "display_name": "限流自测"}
    client.post("/api/auth/register", json=user2)
    r = client.post("/api/auth/login", json={"account": user2["username"], "password": user2["password"]})
    csrf2 = r.json()["csrf_token"]
    statuses = [post_json(client, "/api/translate", {"text": "预检分诊", "src": "zh", "tgt": "en"},
                          csrf2).status_code for _ in range(11)]
    check("translate 限流 10 次/分钟后 429",
          statuses[:10] == [200] * 10 and statuses[10] == 429, f"statuses={statuses}")
    qa_statuses = [post_json(client, "/api/qa", {"question": "分诊标准是什么？"}, csrf2).status_code
                   for _ in range(21)]
    check("qa 限流 20 次/分钟后 429",
          qa_statuses[:20] == [200] * 20 and qa_statuses[20] == 429,
          f"tail={qa_statuses[-3:]}")

# ---------- 11. 清理测试账号 ----------
with SessionLocal() as db:
    ids = [u.id for u in db.scalars(select(User).where(User.username.like(f"ai_selftest%{suffix}"))).all()]
    db.execute(delete(AuditLog).where(AuditLog.user_id.in_(ids)))
    db.execute(delete(User).where(User.id.in_(ids)))
    db.commit()
print(f"cleaned test users: {ids}")

failed = [r for r in results if not r[1]]
print(f"\n==== 结果：{len(results) - len(failed)}/{len(results)} 通过 ====")
sys.exit(1 if failed else 0)
