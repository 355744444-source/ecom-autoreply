# -*- coding: utf-8 -*-
"""消息流模拟器：模拟五平台买家咨询，驱动规则引擎完成自动回复。

真实接入时，把 Adapter.fetch_messages() 换成开放平台推送/拉取即可，
本模块的 dispatch() 是共用的「收到消息 → 匹配 → 回复 → 落库」管线。
"""
import json
import random
import threading
import datetime

import db
import engine


def _now(offset=0.0):
    return datetime.datetime.now() + datetime.timedelta(seconds=offset)


CATEGORY_WEIGHTS = [
    ("物流", 22), ("欢迎", 18), ("尺码", 12), ("优惠", 14),
    ("退换", 10), ("质量", 7), ("发票", 6), ("人工", 5),
]


def pick_category():
    total = sum(w for _, w in CATEGORY_WEIGHTS)
    r = random.uniform(0, total)
    acc = 0
    for cat, w in CATEGORY_WEIGHTS:
        acc += w
        if r <= acc:
            return cat
    return "欢迎"


class Dispatcher:
    """共用回复管线，模拟器与手动注入都走这里。"""

    @staticmethod
    def global_rate_ok(settings):
        con = db.connect()
        since = (_now(-60)).strftime("%Y-%m-%d %H:%M:%S")
        c = con.execute("SELECT COUNT(*) c FROM logs WHERE ts >= ? AND mode='auto'", (since,)).fetchone()["c"]
        con.close()
        return c < int(settings.get("max_per_minute") or 20)

    @staticmethod
    def session_cooldown_ok(session_id, settings):
        con = db.connect()
        row = con.execute(
            "SELECT ts FROM messages WHERE session_id=? AND role='agent' ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        con.close()
        if not row:
            return True
        try:
            last = datetime.datetime.strptime(row["ts"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return True
        gap = (datetime.datetime.now() - last).total_seconds()
        return gap >= int(settings.get("same_session_cooldown") or 60)

    @staticmethod
    def dispatch(session_id, text, platform, platform_name, source="buyer"):
        """写入买家消息并尝试自动回复。返回结果字典。"""
        settings = db.get_settings()
        con = db.connect()
        sess_row = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not sess_row:
            con.close()
            return {"ok": False, "reason": "session not found"}
        session = dict(sess_row)

        ts = db.now_str()
        con.execute(
            "INSERT INTO messages(session_id,role,content,platform,ts,source) VALUES(?,?,?,?,?,?)",
            (session_id, "buyer", text, platform, ts, source),
        )
        con.execute(
            "UPDATE sessions SET last_message=?, last_time=?, unread=unread+1 WHERE id=?",
            ("买家：" + text, ts, session_id),
        )
        con.commit()
        con.close()

        result = {"ok": True, "replied": False, "rule": None, "reply": "", "blocked": False, "reason": ""}

        try:
            if not settings.get("global_enabled"):
                result["reason"] = "全局自动回复已暂停"
                return result
            if session.get("status") == "human":
                result["reason"] = "该会话已转人工，自动回复静默"
                return result
            if not engine.within_hours(settings.get("work_hours") or "") and not settings.get("night_reply"):
                result["reason"] = "非工作时段"
                return result
            if not Dispatcher.session_cooldown_ok(session_id, settings):
                result["reason"] = "同会话冷却中"
                return result
            if not Dispatcher.global_rate_ok(settings):
                result["reason"] = "触发每分钟发送上限"
                return result

            con = db.connect()
            rules = [dict(r) for r in con.execute("SELECT * FROM rules ORDER BY priority DESC, id ASC")]
            con.close()

            rule, hits = engine.match_rule(
                text, platform, rules, allow_fallback=bool(settings.get("fallback_enabled", True))
            )
            if not rule:
                result["reason"] = "没有匹配到任何规则"
                Dispatcher._log(platform, session, text, None, "", "no_match")
                return result

            ctx = engine.build_context(session, settings, platform_name)
            reply = engine.build_reply(rule, ctx, settings)
            blocked, word = engine.filter_sensitive(reply, settings.get("sensitive_words"))
            if blocked:
                result.update({"blocked": True, "reason": "回复触发敏感词「%s」，已拦截" % word,
                               "rule": rule.get("name")})
                Dispatcher._log(platform, session, text, rule, reply, "blocked")
                return result

            delay = random.uniform(
                float(settings.get("reply_delay_min") or 0),
                max(float(settings.get("reply_delay_max") or 1), float(settings.get("reply_delay_min") or 0) + 0.1),
            )
            if delay > 0:
                threading.Event().wait(min(delay, 3.0))

            ts2 = db.now_str()
            con = db.connect()
            con.execute(
                "INSERT INTO messages(session_id,role,content,platform,ts,source) VALUES(?,?,?,?,?,?)",
                (session_id, "agent", reply, platform, ts2, "auto"),
            )
            con.execute("UPDATE sessions SET last_message=?, last_time=?, status='auto' WHERE id=?",
                        ("我：" + reply.split("\n")[0][:40], ts2, session_id))
            con.execute("UPDATE rules SET hits=hits+1 WHERE id=?", (rule.get("id"),))
            con.commit()
            con.close()

            Dispatcher._log(platform, session, text, rule, reply, "auto")
            result.update({"replied": True, "rule": rule.get("name"), "reply": reply,
                           "rule_id": rule.get("id"), "keywords": hits})
            return result
        except Exception as exc:  # 兜底，避免单条消息打断整个服务
            result["reason"] = "处理异常：%s" % exc
            return result

    @staticmethod
    def _log(platform, session, question, rule, reply, mode):
        con = db.connect()
        con.execute(
            "INSERT INTO logs(ts,platform,buyer,session_id,question,rule_id,rule_name,reply,mode,latency_ms)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (db.now_str(), platform, session.get("buyer", ""), session.get("id", ""), question,
             (rule or {}).get("id") if rule else None, (rule or {}).get("name", "") if rule else "",
             reply, mode, random.randint(4, 40)),
        )
        con.commit()
        con.close()


class Simulator(threading.Thread):
    """后台线程：按随机间隔制造买家消息，让界面始终有真实活水。"""

    daemon = True

    def __init__(self, interval=(7.0, 16.0)):
        super().__init__(name="simulator")
        self.interval = interval
        self._stop = threading.Event()
        self.paused = False
        self.tick_count = 0

    def stop(self):
        self._stop.set()

    def run(self):
        self._stop.wait(2.5)
        while not self._stop.is_set():
            try:
                if not self.paused:
                    self.tick()
            except Exception as exc:
                try:
                    import sys
                    if sys.stdout is not None:
                        print("[sim] tick error:", exc)
                except Exception:
                    pass
            self._stop.wait(random.uniform(*self.interval))

    def tick(self):
        settings = db.get_settings()
        if not settings.get("global_enabled"):
            return
        con = db.connect()
        plats = [dict(r) for r in con.execute(
            "SELECT * FROM platforms WHERE enabled=1 AND mode='demo'")]
        con.close()
        if not plats:
            return
        plat = random.choice(plats)
        con = db.connect()
        sess = con.execute(
            "SELECT * FROM sessions WHERE platform=? AND closed=0 ORDER BY RANDOM() LIMIT 1",
            (plat["id"],),
        ).fetchone()
        con.close()

        if not sess:
            sess_id = "s_%d" % random.randint(100000, 999999)
            sess = {"id": sess_id, "platform": plat["id"],
                    "buyer": random.choice(db.BUYER_NAMES),
                    "product": random.choice(db.PRODUCTS),
                    "order_no": "%s%d" % (plat["short"], random.randint(10 ** 11, 10 ** 12 - 1)),
                    "status": "auto"}
            con = db.connect()
            con.execute(
                "INSERT INTO sessions(id,platform,buyer,product,order_no,last_message,last_time,unread,status)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (sess_id, plat["id"], sess["buyer"], sess["product"], sess["order_no"],
                 "", db.now_str(), 0, "auto"),
            )
            con.commit()
            con.close()

        cat = pick_category()
        text = random.choice(db.QUESTIONS.get(cat, ["在吗"]))
        self.tick_count += 1
        Dispatcher.dispatch(sess["id"], text, plat["id"], plat["name"], source="buyer")

    def inject(self, platform=None, session_id=None, text=None):
        """外部触发一条消息（前端「模拟咨询」按钮 / 演示用）。"""
        con = db.connect()
        if platform:
            plat = con.execute("SELECT * FROM platforms WHERE id=?", (platform,)).fetchone()
        else:
            plat = con.execute("SELECT * FROM platforms WHERE enabled=1 LIMIT 1").fetchone()
        if not plat:
            con.close()
            return {"ok": False, "reason": "没有启用中的平台"}
        plat = dict(plat)
        if session_id:
            sess = con.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            sess = dict(sess) if sess else None
        else:
            sess = con.execute(
                "SELECT * FROM sessions WHERE platform=? AND closed=0 ORDER BY last_time DESC LIMIT 1",
                (plat["id"],)).fetchone()
            sess = dict(sess) if sess else None
        con.close()

        if not sess:
            sid = "s_%d" % random.randint(100000, 999999)
            sess = {"id": sid, "platform": plat["id"], "buyer": random.choice(db.BUYER_NAMES),
                    "product": random.choice(db.PRODUCTS),
                    "order_no": "%s%d" % (plat["short"], random.randint(10 ** 11, 10 ** 12 - 1)),
                    "status": "auto"}
            con = db.connect()
            con.execute(
                "INSERT INTO sessions(id,platform,buyer,product,order_no,last_message,last_time,unread,status)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (sid, plat["id"], sess["buyer"], sess["product"], sess["order_no"], "", db.now_str(), 0, "auto"),
            )
            con.commit()
            con.close()

        text = text or random.choice(db.QUESTIONS.get(pick_category(), ["在吗"]))
        res = Dispatcher.dispatch(sess["id"], text, plat["id"], plat["name"], source="buyer")
        res["session_id"] = sess["id"]
        res["platform"] = plat["id"]
        res["text"] = text
        return res
