# -*- coding: utf-8 -*-
"""HTTP 服务：静态页面 + REST API（仅依赖 Python 标准库）。"""
import io
import os
import re
import sys
import csv
import json
import time
import random
import datetime
import socketserver
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

import db
import engine
import simulator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    WEB_DIR = os.path.join(sys._MEIPASS, "web")   # PyInstaller 解包目录
else:
    WEB_DIR = os.path.join(BASE_DIR, "web")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

SIM = simulator.Simulator()


def today_str():
    return datetime.date.today().strftime("%Y-%m-%d")


# ---------------------------------------------------------------- 数据装配
def list_rules():
    con = db.connect()
    data = []
    for r in con.execute("SELECT * FROM rules ORDER BY priority DESC, id ASC"):
        d = dict(r)
        d["platforms"] = json.loads(d.get("platforms") or "[]")
        d["keywords"] = json.loads(d.get("keywords") or "[]")
        data.append(d)
    con.close()
    return data


def list_platforms():
    con = db.connect()
    data = [dict(r) for r in con.execute("SELECT * FROM platforms ORDER BY rowid")]
    counts = {r["platform"]: r["c"] for r in con.execute(
        "SELECT platform, COUNT(DISTINCT session_id) c FROM messages WHERE ts LIKE ? GROUP BY platform",
        (today_str() + "%",))}
    con.close()
    for p in data:
        p["today_sessions"] = counts.get(p["id"], 0)
    return data


def platform_map():
    return {p["id"]: p for p in list_platforms()}


def bootstrap():
    settings = db.get_settings()
    return {
        "settings": settings,
        "platforms": list_platforms(),
        "rules": list_rules(),
        "stats": stats(),
        "server_time": db.now_str(),
    }


def stats():
    con = db.connect()
    today = today_str()
    sessions_today = con.execute(
        "SELECT COUNT(DISTINCT session_id) c FROM messages WHERE ts LIKE ?", (today + "%",)
    ).fetchone()["c"]
    buyer_msgs = con.execute(
        "SELECT COUNT(*) c FROM messages WHERE role='buyer' AND ts LIKE ?", (today + "%",)
    ).fetchone()["c"]
    auto_msgs = con.execute(
        "SELECT COUNT(*) c FROM logs WHERE mode='auto' AND ts LIKE ?", (today + "%",)
    ).fetchone()["c"]
    blocked = con.execute(
        "SELECT COUNT(*) c FROM logs WHERE mode='blocked' AND ts LIKE ?", (today + "%",)
    ).fetchone()["c"]
    no_match = con.execute(
        "SELECT COUNT(*) c FROM logs WHERE mode='no_match' AND ts LIKE ?", (today + "%",)
    ).fetchone()["c"]
    human = con.execute("SELECT COUNT(*) c FROM sessions WHERE status='human' AND closed=0").fetchone()["c"]
    avg_latency = con.execute(
        "SELECT COALESCE(AVG(latency_ms),0) v FROM logs WHERE mode='auto'"
    ).fetchone()["v"]
    total_rules = con.execute("SELECT COUNT(*) c FROM rules WHERE enabled=1").fetchone()["c"]
    hits_30 = con.execute("SELECT COUNT(*) c FROM logs WHERE mode='auto'").fetchone()["c"]

    # 近 7 天趋势
    trend = []
    for i in range(6, -1, -1):
        day = (datetime.date.today() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        a = con.execute("SELECT COUNT(*) c FROM logs WHERE mode='auto' AND ts LIKE ?", (day + "%",)).fetchone()["c"]
        m = con.execute("SELECT COUNT(*) c FROM messages WHERE role='buyer' AND ts LIKE ?", (day + "%",)).fetchone()["c"]
        trend.append({"day": day[5:], "auto": a, "buyer": m})

    top_rules = [dict(r) for r in con.execute(
        "SELECT id,name,hits FROM rules WHERE hits>0 ORDER BY hits DESC LIMIT 6")]
    con.close()

    return {
        "sessions_today": sessions_today,
        "buyer_msgs": buyer_msgs,
        "auto_replies": auto_msgs,
        "blocked": blocked,
        "no_match": no_match,
        "human_takeover": human,
        "hit_rate": round(auto_msgs / buyer_msgs * 100, 1) if buyer_msgs else 0.0,
        "avg_latency": round(float(avg_latency), 1),
        "active_rules": total_rules,
        "total_hits": hits_30,
        "trend": trend,
        "top_rules": top_rules,
    }


def sessions_payload():
    con = db.connect()
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM sessions WHERE closed=0 ORDER BY last_time DESC LIMIT 60")]
    con.close()
    pm = platform_map()
    for s in rows:
        p = pm.get(s["platform"], {})
        s["platform_name"] = p.get("name", s["platform"])
        s["platform_color"] = p.get("color", "#666")
        s["platform_short"] = p.get("short", "?")
    return rows


# ---------------------------------------------------------------- 请求处理
class Handler(BaseHTTPRequestHandler):
    server_version = "AutoReply/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    # ---------- 工具
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False))

    def _err(self, msg, code=400):
        self._json({"ok": False, "error": msg}, code)

    def _body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return {}

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    # ---------- 静态
    def _static(self, path):
        rel = unquote(path.split("?")[0]).lstrip("/")
        if rel in ("", "/"):
            rel = "index.html"
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(os.path.normpath(WEB_DIR)):
            return self._err("forbidden", 403)
        if not os.path.isfile(full):
            return self._send(404, "Not Found", "text/plain; charset=utf-8")
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            data = f.read()
        self._send(200, data, MIME.get(ext, "application/octet-stream"))

    # ---------- GET
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)

        if not path.startswith("/api/"):
            return self._static(path)

        try:
            if path == "/api/bootstrap":
                return self._json(bootstrap())
            if path == "/api/stats":
                return self._json(stats())
            if path == "/api/rules":
                return self._json({"ok": True, "items": list_rules(),
                                   "match_types": engine.MATCH_TYPES, "var_hints": engine.VAR_HINTS})
            if path == "/api/templates":
                con = db.connect()
                items = [dict(r) for r in con.execute("SELECT * FROM templates ORDER BY category, id")]
                con.close()
                for it in items:
                    it["tags"] = json.loads(it.get("tags") or "[]")
                cats = []
                for it in items:
                    if it["category"] not in cats:
                        cats.append(it["category"])
                return self._json({"ok": True, "items": items, "categories": cats})
            if path == "/api/sessions":
                return self._json({"ok": True, "items": sessions_payload()})
            m = re.match(r"^/api/sessions/([\w\-]+)/messages$", path)
            if m:
                sid = m.group(1)
                con = db.connect()
                msgs = [dict(r) for r in con.execute(
                    "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC LIMIT 300", (sid,))]
                con.execute("UPDATE sessions SET unread=0 WHERE id=?", (sid,))
                con.commit()
                con.close()
                return self._json({"ok": True, "items": msgs})
            if path == "/api/feed":
                since = int((q.get("since") or ["0"])[0])
                con = db.connect()
                logs = [dict(r) for r in con.execute(
                    "SELECT * FROM logs WHERE id>? ORDER BY id ASC LIMIT 60", (since,))]
                max_id = con.execute("SELECT COALESCE(MAX(id),0) v FROM logs").fetchone()["v"]
                con.close()
                return self._json({"ok": True, "logs": logs, "cursor": max_id,
                                   "sessions": sessions_payload(), "stats": stats()})
            if path == "/api/logs":
                page = int((q.get("page") or ["1"])[0])
                size = int((q.get("size") or ["30"])[0])
                plat = (q.get("platform") or [""])[0]
                kw = (q.get("q") or [""])[0]
                mode = (q.get("mode") or [""])[0]
                where, args = ["1=1"], []
                if plat:
                    where.append("platform=?")
                    args.append(plat)
                if mode:
                    where.append("mode=?")
                    args.append(mode)
                if kw:
                    where.append("(question LIKE ? OR reply LIKE ? OR buyer LIKE ?)")
                    args += ["%" + kw + "%"] * 3
                w = " AND ".join(where)
                con = db.connect()
                total = con.execute("SELECT COUNT(*) c FROM logs WHERE " + w, args).fetchone()["c"]
                rows = [dict(r) for r in con.execute(
                    "SELECT * FROM logs WHERE " + w + " ORDER BY id DESC LIMIT ? OFFSET ?",
                    args + [size, (page - 1) * size])]
                con.close()
                pm = platform_map()
                for r in rows:
                    r["platform_name"] = pm.get(r["platform"], {}).get("name", r["platform"])
                    r["platform_color"] = pm.get(r["platform"], {}).get("color", "#999")
                return self._json({"ok": True, "items": rows, "total": total, "page": page, "size": size})
            if path == "/api/logs/export.csv":
                con = db.connect()
                rows = [dict(r) for r in con.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 5000")]
                con.close()
                buf = io.StringIO()
                wr = csv.writer(buf)
                wr.writerow(["时间", "平台", "买家", "买家问题", "命中规则", "回复内容", "模式", "耗时ms"])
                mode_cn = {"auto": "自动回复", "blocked": "敏感词拦截", "no_match": "未命中"}
                pm = platform_map()
                for r in rows:
                    wr.writerow([r["ts"], pm.get(r["platform"], {}).get("name", r["platform"]), r["buyer"],
                                 r["question"], r["rule_name"], r["reply"],
                                 mode_cn.get(r["mode"], r["mode"]), r["latency_ms"]])
                data = ("\ufeff" + buf.getvalue()).encode("utf-8")
                fn = "autoreply_logs_%s.csv" % datetime.datetime.now().strftime("%Y%m%d_%H%M")
                return self._send(200, data, "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="%s"' % fn})
            if path == "/api/settings":
                return self._json({"ok": True, "settings": db.get_settings()})
            return self._err("unknown api: " + path, 404)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return self._err("server error: %s" % exc, 500)

    # ---------- POST / PUT / DELETE
    def do_POST(self):
        self._mutate("POST")

    def do_PUT(self):
        self._mutate("PUT")

    def do_DELETE(self):
        self._mutate("DELETE")

    def _mutate(self, method):
        path = urlparse(self.path).path
        try:
            if method == "POST" and path == "/api/rules":
                return self._save_rule(self._body())
            m = re.match(r"^/api/rules/(\d+)$", path)
            if m:
                if method == "DELETE":
                    con = db.connect()
                    con.execute("DELETE FROM rules WHERE id=?", (m.group(1),))
                    con.commit()
                    con.close()
                    return self._json({"ok": True})
                return self._save_rule(self._body(), int(m.group(1)))
            m = re.match(r"^/api/rules/(\d+)/toggle$", path)
            if m and method == "POST":
                con = db.connect()
                con.execute("UPDATE rules SET enabled = 1-enabled WHERE id=?", (m.group(1),))
                con.commit()
                row = con.execute("SELECT enabled FROM rules WHERE id=?", (m.group(1),)).fetchone()
                con.close()
                return self._json({"ok": True, "enabled": row["enabled"] if row else 0})

            if method == "POST" and path == "/api/templates":
                return self._save_template(self._body())
            m = re.match(r"^/api/templates/(\d+)$", path)
            if m:
                if method == "DELETE":
                    con = db.connect()
                    con.execute("DELETE FROM templates WHERE id=?", (m.group(1),))
                    con.commit()
                    con.close()
                    return self._json({"ok": True})
                return self._save_template(self._body(), int(m.group(1)))

            if method == "POST" and path == "/api/test":
                b = self._body()
                platform = b.get("platform") or "tmall"
                pm = platform_map()
                sess = {"buyer": b.get("buyer") or "亲",
                        "product": b.get("product") or "纯棉宽松短袖T恤",
                        "order_no": b.get("order_no") or "TM20261017000001"}
                res = engine.test_match(b.get("text") or "", platform, list_rules(), sess,
                                        db.get_settings(), pm.get(platform, {}).get("name", platform))
                res["ok"] = True
                return self._json(res)

            m = re.match(r"^/api/sessions/([\w\-]+)/send$", path)
            if m and method == "POST":
                b = self._body()
                sid = m.group(1)
                text = (b.get("text") or "").strip()
                if not text:
                    return self._err("回复内容不能为空")
                con = db.connect()
                sess = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
                if not sess:
                    con.close()
                    return self._err("会话不存在", 404)
                ts = db.now_str()
                con.execute("INSERT INTO messages(session_id,role,content,platform,ts,source)"
                            " VALUES(?,?,?,?,?,?)", (sid, "agent", text, sess["platform"], ts, "manual"))
                con.execute("UPDATE sessions SET last_message=?, last_time=?, unread=0, status='human' WHERE id=?",
                            ("我：" + text[:40], ts, sid))
                con.commit()
                con.close()
                return self._json({"ok": True})

            m = re.match(r"^/api/sessions/([\w\-]+)/status$", path)
            if m and method == "POST":
                b = self._body()
                status = b.get("status") or "auto"
                con = db.connect()
                con.execute("UPDATE sessions SET status=?, unread=0 WHERE id=?", (status, m.group(1)))
                con.commit()
                con.close()
                return self._json({"ok": True})

            m = re.match(r"^/api/platforms/([\w\-]+)$", path)
            if m and method in ("POST", "PUT"):
                b = self._body()
                fields, args = [], []
                for k in ("enabled", "mode", "app_key", "app_secret", "shop", "status"):
                    if k in b:
                        fields.append("%s=?" % k)
                        args.append(b[k])
                if not fields:
                    return self._err("没有需要更新的字段")
                args.append(m.group(1))
                con = db.connect()
                con.execute("UPDATE platforms SET " + ",".join(fields) + " WHERE id=?", args)
                con.commit()
                con.close()
                return self._json({"ok": True, "platforms": list_platforms()})

            if method == "POST" and path == "/api/settings":
                patch = self._body()
                db.set_settings(patch)
                return self._json({"ok": True, "settings": db.get_settings()})

            if method == "POST" and path == "/api/simulate":
                b = self._body()
                res = SIM.inject(platform=b.get("platform"),
                                 session_id=b.get("session_id"), text=b.get("text"))
                return self._json(res)

            if method == "POST" and path == "/api/simulator":
                b = self._body()
                if "paused" in b:
                    SIM.paused = bool(b["paused"])
                return self._json({"ok": True, "paused": SIM.paused})

            if method == "POST" and path == "/api/logs/clear":
                con = db.connect()
                con.execute("DELETE FROM logs")
                con.commit()
                con.close()
                return self._json({"ok": True})

            if method == "POST" and path == "/api/sessions/reset":
                con = db.connect()
                con.execute("DELETE FROM messages")
                con.execute("DELETE FROM sessions")
                con.commit()
                con.close()
                return self._json({"ok": True})

            return self._err("unknown api: " + path, 404)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return self._err("server error: %s" % exc, 500)

    # ---------- 保存实体
    def _save_rule(self, b, rid=None):
        name = (b.get("name") or "").strip()
        if not name:
            return self._err("规则名称不能为空")
        if not (b.get("reply") or "").strip():
            return self._err("回复内容不能为空")
        mt = b.get("match_type") or "any"
        kws = b.get("keywords") or []
        if isinstance(kws, str):
            kws = [k.strip() for k in re.split(r"[,，\n]", kws) if k.strip()]
        if mt not in ("fallback",) and not kws:
            return self._err("请至少填写一个关键词")
        if mt == "regex" and kws:
            try:
                re.compile(kws[0])
            except re.error as e:
                return self._err("正则表达式有误：%s" % e)
        plats = b.get("platforms") or []
        ts = db.now_str()
        vals = (name, json.dumps(plats, ensure_ascii=False), mt,
                json.dumps(kws, ensure_ascii=False), int(b.get("priority") or 50),
                b.get("reply") or "", b.get("work_hours") or "",
                1 if b.get("enabled", 1) else 0,
                1 if mt == "fallback" or b.get("is_fallback") else 0,
                b.get("note") or "", ts)
        con = db.connect()
        if rid:
            con.execute(
                "UPDATE rules SET name=?,platforms=?,match_type=?,keywords=?,priority=?,reply=?,"
                "work_hours=?,enabled=?,is_fallback=?,note=?,updated_at=? WHERE id=?",
                vals + (rid,))
        else:
            con.execute(
                "INSERT INTO rules(name,platforms,match_type,keywords,priority,reply,work_hours,"
                "enabled,is_fallback,note,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", vals)
            rid = con.execute("SELECT last_insert_rowid() v").fetchone()["v"]
        con.commit()
        con.close()
        return self._json({"ok": True, "id": rid, "items": list_rules()})

    def _save_template(self, b, tid=None):
        title = (b.get("title") or "").strip()
        content = (b.get("content") or "").strip()
        if not title or not content:
            return self._err("标题与内容不能为空")
        cat = b.get("category") or "通用"
        tags = b.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，\s]", tags) if t.strip()]
        con = db.connect()
        if tid:
            con.execute("UPDATE templates SET category=?,title=?,content=?,tags=? WHERE id=?",
                        (cat, title, content, json.dumps(tags, ensure_ascii=False), tid))
        else:
            con.execute("INSERT INTO templates(category,title,content,tags,uses,created_at) VALUES(?,?,?,?,?,?)",
                        (cat, title, content, json.dumps(tags, ensure_ascii=False), 0, db.now_str()))
            tid = con.execute("SELECT last_insert_rowid() v").fetchone()["v"]
        con.commit()
        con.close()
        return self._json({"ok": True, "id": tid})


class ThreadedHTTP(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def log(*parts):
    """无控制台（打包成 -w 单文件）时 sys.stdout 为 None，输出要安全降级。"""
    if sys.stdout is None:
        return
    try:
        print(*parts)
    except Exception:
        pass


def create_server(host="127.0.0.1", port=8765, start_sim=True):
    """只创建并返回 httpd，由调用方决定在哪个线程里 serve_forever。"""
    db.init_db()
    httpd = ThreadedHTTP((host, port), Handler)
    if start_sim:
        SIM.start()
    return httpd


def shutdown(httpd):
    try:
        SIM.stop()
    except Exception:
        pass
    try:
        httpd.shutdown()
    except Exception:
        pass
    try:
        httpd.server_close()
    except Exception:
        pass


def serve(host="127.0.0.1", port=8765):
    httpd = create_server(host, port)
    log("=" * 56)
    log("  智回 · 电商自动回复工作台")
    log("  服务地址: http://%s:%d" % (host, port))
    log("  数据目录: %s" % db.DB_PATH)
    log("  按 Ctrl+C 停止")
    log("=" * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log("\n正在退出…")
    finally:
        shutdown(httpd)


if __name__ == "__main__":
    serve()
