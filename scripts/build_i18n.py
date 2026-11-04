# -*- coding: utf-8 -*-
"""由 i18n_strings.txt + i18n_en.txt 生成前后端共用的双语字典。

- static/js/i18n-dict.js  -> window.WB_I18N_DATA（浏览器：DOM 文本 / 属性 / 动态串）
- app/i18n_data.py        -> DICT / PHRASES / TEMPLATES（服务端：错误文案 / 问答 / 告知单）

字典以「中文原文」为键，天然保证中英一一对应；切换语言时浏览器重新加载，
中文模式直接渲染源码中的中文，英文模式按字典替换，两种语言覆盖同一批文案。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "i18n_strings.txt"
EN = BASE / "i18n_en.txt"
EXTRA = BASE / "i18n_extra.txt"

# 复合动态串（含数字 / 变量），前端用 I18N.t() 按模板替换
TEMPLATES = {
    "共 {n} 条 · 第 {p} / {t} 页": "Total {n} items · Page {p} / {t}",
    "你好，{name}（@{user}）· 这里的数据仅本人可见": "Hello, {name} (@{user}) · data here is visible only to you",
    "正在加载我的{tab}…": "Loading my {tab}…",
    "提问失败：{msg}": "Question failed: {msg}",
    "删除失败：{msg}": "Delete failed: {msg}",
    "详情加载失败：{msg}": "Details failed to load: {msg}",
    "共 {n} 条资讯": "Total {n} news items",
    "共 {n} 条 · 英语变体 {v} 条 · 覆盖 {c} 个国家与地区":
        "{n} cultural expressions · {v} English variants · covering {c} countries and regions",
    "文化表达 {n} 条 · 英语变体 {v} 条 · 覆盖 {c} 个国家与地区":
        "{n} cultural expressions · {v} English variants · covering {c} countries and regions",
    "第 {p} / {t} 页": "Page {p} / {t}",
    "已恢复本地草稿（{time}）": "Local draft restored ({time})",
    "超出 {n} 字上限，已截断为 {m}": "Exceeds {n} character limit, truncated to {m}",
    "内容超过 {n} 字，已截断": "Input exceeds {n} characters, truncated",
    "恢复草稿（{time}）": "Restore draft ({time})",
    "粘贴的 {n} 字": "Pasted {n} characters",
    "输入的 {n} 字": "Entered {n} characters",
    "导入完成：成功 {a} 条，跳过 {b} 条（已存在），失败 {c} 条":
        "Import complete: {a} succeeded, {b} skipped (already present), {c} failed",
    "已导出文件（{n} 条）": "File exported ({n} items)",
    "后端导出接口未启用，已在前端生成 JSON（{n} 条）。":
        "Backend export endpoint not enabled; JSON generated in the browser ({n} items).",
    "本地语 1,040 条为只读对照数据": "The 1,040 local-language items are read-only reference data",
    "公共 · 当前 {n} 条": "Public · current {n} items",
    "第 {p} 页 / 共 {t} 页": "Page {p} / {t}",
    "已载入患者情况告知单（{time}）": "Loaded Patient Handoff Sheet ({time})",
    "云端身份已建立（{email}），会话自动附加到数据库与存储请求":
        "Cloud identity established ({email}); session automatically attached to database and storage requests",
    "已写入云端（id={id}），下面列表为读回结果":
        "Written to cloud (id={id}); the list below is the read-back result",
    "数据库写入成功，行 id={id}": "Database write succeeded, row id={id}",
    "数据库读取成功，返回 {n} 条（仅本人可见）":
        "Database read succeeded, returned {n} rows (visible only to you)",
    "已删除记录 #{id}": "Deleted record #{id}",
    "存储列表读取成功，共 {n} 个对象": "Storage list read succeeded, {n} objects",
    "已签发 10 分钟有效的下载链接并在新标签打开":
        "A 10-minute download link was issued and opened in a new tab",
    "模型目录读取成功，共 {n} 个可用模型，默认 {m}":
        "Model catalogue read succeeded, {n} models available, default {m}",
    "模型调用完成，total_tokens={n}": "Model call completed, total_tokens={n}",
    "LLM 流式调用结束，输出 {n} 字": "LLM stream finished, output {n} characters",
    "生成完成（模型 {m}）": "Generation complete (model {m})",
    "我的条目（{n}）": "My entries ({n})",
    "{n} 条": "{n} items",
    "{n} 句": "{n} sentences",
    "{n} 个": "{n}",
    "{n} 片": "{n} chunks",
    "共 {n} 条": "Total {n} items",
    "第 {p} 页": "Page {p}",
    "共 {n} 条 · 第 {p} 页": "Total {n} items · Page {p}",
    "{name}（{code}）": "{name} ({code})",
    "{scope}{tab} · 当前 {n} 条": "{scope} {tab} · Current {n} items",
    "搜索{tab}…": "Search {tab}…",
    "{tab}{scope}": "{tab}{scope}",
    "共 {n} 条，仅显示前 5 条。": "Total {n} items, showing the first 5 only.",
    "后端导出接口未启用，已在前端生成 JSON（{n} 条）。":
        "Backend export endpoint not enabled; JSON generated in the browser ({n} items).",
    "导入完成：成功 {a} 条，跳过 {b} 条（已存在），失败 {c} 条":
        "Import complete: {a} succeeded, {b} skipped (already present), {c} failed",
    "主诉：{text}": "Chief complaint: {text}",
    "01  不适部位：{text}": "01  Affected areas: {text}",
    "02  不适症状：{text}": "02  Symptoms: {text}",
    "03  症状细节：": "03  Symptom details:",
    "04  患者原话（照录）：{text}": "04  Patient's own words (verbatim): {text}",
    "05  沟通对象文化 / 国家：{text}": "05  Communication partner culture / country: {text}",
    "【患者情况告知单 · {scene}】": "[Patient Handoff Sheet · {scene}]",
}

# 2 字及以上的短语用于「片段 / 复合串」的子串替换；为避免误伤语料数据，
# 只取含 3 个及以上汉字的键，另加一小撮辨识度高的 2 字 UI 词。
STOP_2 = {
    "中文", "英文", "原文", "译文", "术语", "语料", "患者", "医院", "医生", "护士",
    "急诊", "翻译", "表达", "国家", "类型", "领域", "语种", "程度", "性质", "场景",
    "其他", "全部", "来源", "知识", "服务", "标准", "相关", "关于", "用语", "对照",
    "意思", "说法", "请问", "怎么", "如何", "什么", "可以", "哪些", "是否", "需要",
    "一下", "多少", "用语", "条", "页", "句", "片", "个", "字", "共", "第", "输入",
}
EXTRA_2 = ["超出", "草稿", "暂无", "收起", "重译", "清空", "复制", "删除", "保存",
           "取消", "确认", "编辑", "新建", "登录", "注册", "发送", "关闭", "提示",
           "操作", "导出", "导入", "重置", "搜索", "详情", "展开", "历史", "清单"]


def cjk_count(s: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def main() -> None:
    src = [line.rstrip("\n").split("\t") for line in SRC.read_text(encoding="utf-8").splitlines()]
    en = [line.rstrip("\n").split("\t") for line in EN.read_text(encoding="utf-8").splitlines() if line.strip()]
    extra = [line.rstrip("\n").split("\t") for line in EXTRA.read_text(encoding="utf-8").splitlines() if line.strip()]

    assert len(src) == 982, "i18n_strings.txt 行数变化，请重新核对"
    main_en = {p[0]: p[1] for p in en if p[0].isdigit()}
    ext_en = {p[0]: p[1] for p in en if p[0].startswith("E")}
    assert len(main_en) == len(src), "主字典索引不全"
    assert len(ext_en) == len(extra), "附加标签索引不全"

    entries: list[tuple[str, str]] = []
    skipped = 0
    for idx, zh, _files in src:
        value = main_en[idx]
        if value.strip() == "-":
            skipped += 1
            continue
        entries.append((zh, value))
    for idx, zh in extra:
        value = ext_en[idx]
        if value.strip() == "-":
            continue
        entries.append((zh, value))

    # 去重（保留第一次出现）
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for zh, value in entries:
        if zh in seen:
            continue
        seen.add(zh)
        uniq.append((zh, value))

    # 冲突检查：同一个英文对应多个中文时给出提示（不阻断，翻译仍可用）
    reverse: dict[str, list[str]] = {}
    for zh, value in uniq:
        reverse.setdefault(value, []).append(zh)

    # 子串替换用短语：长键优先
    phrases: list[tuple[str, str]] = []
    for zh, value in uniq:
        if "<" in zh or '="' in zh or zh.startswith('"'):
            continue
        n = cjk_count(zh)
        if n >= 3 or (n == 2 and zh in EXTRA_2 and zh not in STOP_2):
            phrases.append((zh, value))
    phrases.sort(key=lambda pair: len(pair[0]), reverse=True)
    # 模板也参与子串替换，保证含变量的复合串可翻译
    templates = dict(TEMPLATES)

    js_obj = {
        "dict": dict(uniq),
        "phrases": [list(p) for p in phrases],
        "templates": templates,
        "meta": {"zh": len(src), "entries": len(uniq), "phrases": len(phrases),
                 "skipped": skipped, "templates": len(templates)},
    }
    js = "/* 自动生成，勿手改；源：i18n_strings.txt / i18n_en.txt / i18n_extra.txt */\n" + \
         "window.WB_I18N_DATA = " + json.dumps(js_obj, ensure_ascii=False, indent=1) + ";\n"
    (BASE / "static" / "js" / "i18n-dict.js").write_text(js, encoding="utf-8")

    py = ("# -*- coding: utf-8 -*-\n"
          '"""自动生成，勿手改：与前端 i18n-dict.js 共用同一份中英对照。"""\n'
          "DICT = " + repr(dict(uniq)) + "\n\n"
          "PHRASES = " + repr([list(p) for p in phrases]) + "\n\n"
          "TEMPLATES = " + repr(templates) + "\n\n"
          'LANGS = ("zh", "en")\n')
    (BASE / "app" / "i18n_data.py").write_text(py, encoding="utf-8")

    report = {
        "source_strings": len(src), "extra_labels": len(extra),
        "dict_entries": len(uniq), "skipped_fragments": skipped,
        "phrase_keys": len(phrases), "templates": len(templates),
        "duplicate_en_values": {k: v for k, v in reverse.items() if len(v) > 1},
        "meta": js_obj["meta"],
    }
    (BASE / "i18n_coverage.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("built:", js_obj["meta"])


if __name__ == "__main__":
    main()
