# -*- coding: utf-8 -*-
"""向量检索服务 · 纯标准库 HTTP API（无 fastapi/flask 依赖）。

启动：
    python work/vector_db/api_server.py --port 8848
    python work/vector_db/api_server.py --selftest      # 内建自测：起服务并打全部接口

接口：
    GET  /health                          -> {"status":"ok","docs":14400,"dim":1024}
    GET  /search?q=...&k=8&source=term    -> 检索结果列表
    GET  /term/<doc_id>                   -> 单条详情
    GET  /compare?q=...&k=5               -> 五类来源分组（译法对比）
    POST /batch  {"queries": [...], "k": 8, "source": null} -> 批量检索

设计说明：
  - 索引只在启动时加载一次，进程内共享（SearchIndex 只读）。
  - 每个请求带软超时保护：工作线程超过 --timeout 秒即返回 504，
    工作线程本身无法强杀，但连接与响应会被及时释放。
  - 所有错误统一返回 {"error": {"code": "...", "message": "..."}}。
"""
import argparse
import json
import logging
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INDEX = os.path.join(HERE, "index")
SOURCES = ("term", "corpus", "culture", "local", "real")
VERSION = "1.0.0"

# ---------------------------------------------------------------- 全局状态
IDX = None                 # SearchIndex
IDX_ERROR = None           # 加载失败原因
STATS = {"started": time.time(), "requests": 0}
EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="vdb")
CFG = {"timeout": 20.0, "max_k": 50, "max_batch": 50, "max_q_len": 500, "log": True}

LOG = logging.getLogger("vdb")


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


# ---------------------------------------------------------------- 工具函数
def load_index(index_dir):
    global IDX, IDX_ERROR
    try:
        sys.path.insert(0, HERE)
        from search import SearchIndex  # 复用既有检索实现，不修改它
        IDX = SearchIndex(index_dir=index_dir)
        IDX_ERROR = None
        LOG.info("索引加载完成：%d 条，dim=%d", len(IDX.meta), IDX.dim)
    except Exception as exc:  # noqa: BLE001
        IDX = None
        IDX_ERROR = "%s: %s" % (type(exc).__name__, exc)
        LOG.error("索引加载失败：%s", IDX_ERROR)


def slim(hit):
    """只输出对下游有用的字段，避免把 6KB 的 text 全量返给调用方。"""
    return {
        "score": hit.get("score"),
        "source": hit.get("source"),
        "doc_id": hit.get("doc_id"),
        "zh": hit.get("zh"),
        "en": hit.get("en"),
        "domain": hit.get("domain"),
        "scene": hit.get("scene"),
        "country": hit.get("country"),
        "parent": hit.get("parent"),
    }


def parse_int(raw, default, name, lo=1, hi=None):
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "bad_param", "参数 %s 必须是整数，收到：%r" % (name, raw))
    if val < lo:
        raise ApiError(400, "bad_param", "参数 %s 不能小于 %d" % (name, lo))
    if hi is not None and val > hi:
        raise ApiError(400, "bad_param", "参数 %s 不能大于 %d（当前上限）" % (name, hi))
    return val


def parse_source(raw):
    if raw is None or raw == "" or raw == "all":
        return None
    src = str(raw).strip()
    if src not in SOURCES:
        raise ApiError(400, "bad_source", "source 只能是 %s，收到：%r" % ("/".join(SOURCES), src))
    return src


def require_query(q):
    if q is None:
        raise ApiError(400, "missing_param", "缺少必填参数 q")
    q = str(q).strip()
    if not q:
        raise ApiError(400, "empty_query", "参数 q 不能为空")
    if len(q) > CFG["max_q_len"]:
        raise ApiError(400, "query_too_long", "查询长度超过 %d 字" % CFG["max_q_len"])
    return q


def ensure_index():
    if IDX is None:
        raise ApiError(503, "index_unavailable", "索引未加载：%s" % (IDX_ERROR or "unknown"))


def run_protected(fn):
    """软超时：工作线程超时则抛 504，避免慢查询拖死连接。"""
    ensure_index()
    fut = EXECUTOR.submit(fn)
    try:
        return fut.result(timeout=CFG["timeout"])
    except FutureTimeout:
        raise ApiError(504, "timeout", "检索超时（>%.0f 秒），请缩小 k 或改用更短的查询" % CFG["timeout"])


# ---------------------------------------------------------------- 业务处理
def do_health(_params):
    docs = len(IDX.meta) if IDX is not None else 0
    dim = int(IDX.dim) if IDX is not None else 0
    body = {
        "status": "ok" if IDX is not None else "degraded",
        "docs": docs,
        "dim": dim,
        "sources": {s: len([1 for m in IDX.meta if m["source"] == s]) for s in SOURCES} if IDX is not None else {},
        "version": VERSION,
        "uptime_s": round(time.time() - STATS["started"], 1),
        "requests": STATS["requests"],
    }
    if IDX is None:
        body["error"] = {"code": "index_unavailable", "message": IDX_ERROR or "unknown"}
    return 200, body


def do_search(params):
    q = require_query(params.get("q", [None])[0])
    k = parse_int(params.get("k", [None])[0], 8, "k", 1, CFG["max_k"])
    source = parse_source(params.get("source", [None])[0])

    def work():
        return IDX.search(q, k=k, source=source)

    hits = run_protected(work)
    return 200, {
        "query": q, "k": k, "source": source or "all",
        "count": len(hits), "results": [slim(h) for h in hits],
    }


def do_term(params, doc_id):
    doc_id = unquote(doc_id or "").strip()
    if not doc_id:
        raise ApiError(400, "missing_param", "缺少 doc_id，例如 /term/term-T-0024")

    def work():
        return IDX.get(doc_id)

    hit = run_protected(work)
    if not hit:
        raise ApiError(404, "not_found", "未找到 doc_id=%s" % doc_id)
    out = slim(hit)
    out["text"] = hit.get("text")
    out["i"] = hit.get("i")
    return 200, out


def do_compare(params):
    q = require_query(params.get("q", [None])[0])
    k = parse_int(params.get("k", [None])[0], 5, "k", 1, CFG["max_k"])

    def work():
        return IDX.compare(q, top_k=k)

    groups = run_protected(work)
    body = {"query": q, "k": k, "groups": {}, "total": 0}
    for src in SOURCES:
        hits = groups.get(src) or []
        body["groups"][src] = [slim(h) for h in hits]
        body["total"] += len(hits)
    return 200, body


def do_batch(payload):
    if not isinstance(payload, dict):
        raise ApiError(400, "bad_body", "请求体必须是 JSON 对象")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ApiError(400, "bad_body", "queries 必须是非空数组")
    if len(queries) > CFG["max_batch"]:
        raise ApiError(400, "too_many_queries", "单次批量最多 %d 条" % CFG["max_batch"])
    k = parse_int(payload.get("k"), 8, "k", 1, CFG["max_k"])
    source = parse_source(payload.get("source"))
    qs = [require_query(x) for x in queries]
    started = time.time()

    def work():
        return [[slim(h) for h in IDX.search(q, k=k, source=source)] for q in qs]

    out = run_protected(work)
    return 200, {
        "count": len(qs), "k": k, "source": source or "all",
        "elapsed_ms": int((time.time() - started) * 1000),
        "results": [{"query": q, "hits": hits} for q, hits in zip(qs, out)],
    }


# ---------------------------------------------------------------- HTTP 层
class Handler(BaseHTTPRequestHandler):
    server_version = "VDB/" + VERSION
    protocol_version = "HTTP/1.1"

    # -- 基础工具 ------------------------------------------------------
    def log_message(self, fmt, *args):
        if CFG["log"]:
            LOG.info("%s - %s", self.address_string(), fmt % args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _fail(self, status, code, message):
        self._send(status, {"error": {"code": code, "message": message}})

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "bad_body", "Content-Length 非法")
        if length <= 0:
            raise ApiError(400, "bad_body", "请求体为空")
        if length > 2 * 1024 * 1024:
            raise ApiError(413, "body_too_large", "请求体超过 2MB")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise ApiError(400, "bad_json", "请求体不是合法 JSON：%s" % exc)

    # -- 路由 ----------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        STATS["requests"] += 1
        started = time.time()
        parts = urlsplit(self.path)
        path = parts.path.rstrip("/") or "/"
        params = parse_qs(parts.query, keep_blank_values=True)
        status = 500
        try:
            if method == "GET" and path == "/":
                status, body = 200, {
                    "service": "vector-db",
                    "version": VERSION,
                    "endpoints": ["/health", "/search?q=&k=&source=", "/term/<doc_id>", "/compare?q=&k=", "POST /batch"],
                    "sources": list(SOURCES),
                }
            elif method == "GET" and path == "/health":
                status, body = do_health(params)
            elif method == "GET" and path == "/search":
                status, body = do_search(params)
            elif method == "GET" and path == "/compare":
                status, body = do_compare(params)
            elif method == "GET" and path.startswith("/term/"):
                status, body = do_term(params, path[len("/term/"):])
            elif method == "POST" and path == "/batch":
                status, body = do_batch(self._read_json())
            elif path in ("/health", "/search", "/compare", "/term"):
                raise ApiError(405, "method_not_allowed", "%s 不支持 %s 方法" % (path, method))
            else:
                raise ApiError(404, "not_found", "未知路径：%s" % path)
        except ApiError as exc:
            status, body = exc.status, {"error": {"code": exc.code, "message": exc.message}}
        except Exception as exc:  # noqa: BLE001
            LOG.error("未捕获异常：%s\n%s", exc, traceback.format_exc())
            status, body = 500, {"error": {"code": "internal_error", "message": "%s: %s" % (type(exc).__name__, exc)}}
        self._send(status, body)
        if CFG["log"]:
            LOG.info("%s %s -> %d (%.0f ms)", method, self.path, status, (time.time() - started) * 1000)


def build_server(host, port):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


# ---------------------------------------------------------------- 自测
def selftest(host="127.0.0.1"):
    """起一个临时端口的真实 HTTP 服务，用 urllib 打 5 个接口并打印结果。"""
    import urllib.request
    import urllib.error

    httpd = build_server(host, 0)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = "http://%s:%d" % (host, port)
    print("selftest: listening on %s" % base)

    def call(method, path, payload=None, timeout=60):
        url = base + path
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw), (time.time() - t0) * 1000
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8")), (time.time() - t0) * 1000

    def show(name, status, body, ms, extra="", expect=200):
        ok = "PASS" if status == expect else "FAIL"
        brief = json.dumps(body, ensure_ascii=False)
        if len(brief) > 260:
            brief = brief[:260] + "..."
        print("[%s] %-22s %s %6.0fms %s %s" % (ok, name, status, ms, extra, brief))

    results = []
    st, bd, ms = call("GET", "/health")
    show("GET /health", st, bd, ms); results.append(("GET /health", st, bd, 200))
    doc_hint = None
    st, bd, ms = call("GET", "/search?q=" + urllib.parse.quote("预检分诊") + "&k=8&source=term")
    show("GET /search(term)", st, bd, ms); results.append(("GET /search", st, bd, 200))
    if isinstance(bd, dict) and bd.get("results"):
        doc_hint = bd["results"][0]["doc_id"]
    st, bd, ms = call("GET", "/search?q=triage&k=5")
    show("GET /search(all)", st, bd, ms); results.append(("GET /search(all)", st, bd, 200))
    st, bd, ms = call("GET", "/term/" + urllib.parse.quote(doc_hint or "term-T-0001"))
    show("GET /term/<doc_id>", st, bd, ms); results.append(("GET /term", st, bd, 200))
    st, bd, ms = call("GET", "/compare?q=" + urllib.parse.quote("预检分诊") + "&k=5")
    show("GET /compare", st, bd, ms); results.append(("GET /compare", st, bd, 200))
    st, bd, ms = call("POST", "/batch", {"queries": ["预检分诊", "triage"], "k": 3})
    show("POST /batch", st, bd, ms); results.append(("POST /batch", st, bd, 200))
    # 错误路径也要能返回统一 JSON
    st, bd, ms = call("GET", "/search?q=&k=8")
    show("GET /search(400)", st, bd, ms, expect=400); results.append(("GET /search(400)", st, bd, 400))
    st, bd, ms = call("GET", "/term/does-not-exist")
    show("GET /term(404)", st, bd, ms, expect=404); results.append(("GET /term(404)", st, bd, 404))

    httpd.shutdown()
    ok_n = sum(1 for _, status, _body, expect in results if status == expect)
    print("selftest: %d/%d 成功" % (ok_n, len(results)))
    return 0 if ok_n == len(results) else 1


# ---------------------------------------------------------------- 入口
def main(argv=None):
    ap = argparse.ArgumentParser(description="向量检索 HTTP API（标准库实现）")
    ap.add_argument("--host", default=os.environ.get("VDB_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("VDB_PORT", "8848")))
    ap.add_argument("--index-dir", default=os.environ.get("VDB_INDEX_DIR", DEFAULT_INDEX))
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("VDB_TIMEOUT", "20")))
    ap.add_argument("--max-k", type=int, default=int(os.environ.get("VDB_MAX_K", "50")))
    ap.add_argument("--max-batch", type=int, default=int(os.environ.get("VDB_MAX_BATCH", "50")))
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="起临时服务并自测全部接口")
    ap.add_argument("--version", action="version", version="vdb-api " + VERSION)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    CFG.update(timeout=args.timeout, max_k=args.max_k, max_batch=args.max_batch, log=not args.quiet)

    if args.selftest:
        load_index(args.index_dir)
        if IDX is None:
            print("selftest 失败：索引未加载 %s" % IDX_ERROR)
            return 2
        return selftest()

    load_index(args.index_dir)
    httpd = build_server(args.host, args.port)
    host, port = httpd.server_address[0], httpd.server_address[1]
    print("vector-db API 已启动：http://%s:%d  (docs=%s, dim=%s)" % (
        host, port, len(IDX.meta) if IDX is not None else "?", IDX.dim if IDX is not None else "?"))
    print("试试： curl http://127.0.0.1:%d/health" % port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n收到 Ctrl-C，正在关闭…")
    finally:
        httpd.shutdown()
        httpd.server_close()
        EXECUTOR.shutdown(wait=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())