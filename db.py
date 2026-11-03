# -*- coding: utf-8 -*-
"""数据层：SQLite 建表、种子数据、通用读写工具。"""
import os
import sys
import json
import sqlite3
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 打包成单文件 exe 后，数据要落在 exe 同级目录，而不是临时解包目录
if getattr(sys, "frozen", False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")

# id, 名称, 品牌色, 缩写, 官方开放平台, 说明
PLATFORMS = [
    ("pdd", "拼多多", "#E02E24", "PDD", "拼多多开放平台",
     "需在拼多多商家后台申请应用，获取 client_id / client_secret，订阅客服消息推送。"),
    ("tmall", "天猫", "#FF0036", "TM", "淘宝开放平台（TOP）",
     "需申请「天猫商家客服」类目应用，使用 qimen / 消息服务订阅客服会话。"),
    ("taobao", "淘宝", "#FF5000", "TB", "淘宝开放平台（TOP）",
     "个人店与集市店可申请基础客服接口，需完成店铺授权与回调地址备案。"),
    ("jd", "京东", "#E1251B", "JD", "京东宙斯开放平台",
     "需申请「咚咚客服」接口权限，通过 access_token 拉取会话并回传消息。"),
    ("douyin", "抖音", "#161823", "DY", "抖店开放平台",
     "需开通「飞鸽客服」能力，订阅 im 消息事件，回传消息有 5 秒响应时限。"),
]

DEFAULT_SETTINGS = {
    "global_enabled": True,
    "work_hours": "08:00-23:00",
    "night_reply": True,
    "reply_delay_min": 1,
    "reply_delay_max": 3,
    "max_per_minute": 20,
    "same_session_cooldown": 60,
    "human_takeover_minutes": 5,
    "sensitive_words": ["差评", "投诉", "假货", "骗", "起诉", "曝光"],
    "shop_name": "振远优选旗舰店",
    "agent_name": "小远",
    "append_signature": True,
    "signature": "—— {店铺}客服 {客服名} 为您服务",
    "fallback_enabled": True,
    "log_retention_days": 30,
}

SEED_RULES = [
    {
        "name": "转人工优先",
        "platforms": [],
        "match_type": "any",
        "keywords": ["转人工", "人工客服", "找客服", "人工", "投诉"],
        "priority": 100,
        "reply": "收到～已为您转接人工客服，{客服名}马上就来，请稍等 1 分钟哦 🙌",
        "work_hours": "",
        "is_fallback": 0,
        "note": "命中后建议前端暂停该会话自动回复，交由人工跟进。",
    },
    {
        "name": "催发货",
        "platforms": [],
        "match_type": "any",
        "keywords": ["还没发货", "什么时候发货", "多久发货", "催一下", "怎么还不发", "几天发货"],
        "priority": 95,
        "reply": "亲，您的订单 {订单号} 我们已排单打包，仓库会在 24 小时内发出（节假日顺延 1 天），发货后物流单号会第一时间同步给您～",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "物流查询",
        "platforms": [],
        "match_type": "any",
        "keywords": ["物流", "快递", "到哪了", "运单号", "签收", "派送"],
        "priority": 90,
        "reply": "亲，帮您查到包裹正在运输途中，最新状态：{物流状态}。您也可以在「我的订单」里点开物流详情实时查看哦～",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "退换货政策",
        "platforms": ["tmall", "taobao", "jd"],
        "match_type": "any",
        "keywords": ["退货", "换货", "退款", "七天无理由", "不合适", "不喜欢"],
        "priority": 88,
        "reply": "支持 7 天无理由退换货哦～ 商品不影响二次销售即可，您在订单页点「申请售后」选择退货退款，我们收到后 48 小时内处理完成。",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "质量问题安抚",
        "platforms": [],
        "match_type": "any",
        "keywords": ["破损", "坏了", "少发", "漏发", "质量", "瑕疵", "色差"],
        "priority": 86,
        "reply": "非常抱歉给您带来不好的体验 😔 麻烦拍一张外包装和商品的照片发我，确认后我们立刻为您补发 / 退款，运费我们承担。",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "尺码推荐",
        "platforms": ["tmall", "taobao", "douyin", "pdd"],
        "match_type": "any",
        "keywords": ["尺码", "什么码", "偏大", "偏小", "身高", "体重", "码数"],
        "priority": 84,
        "reply": "亲，告诉我您的身高体重，我帮您选码～ 一般来说 {商品名} 版型正常，喜欢宽松可以选大一码。",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "优惠与满减",
        "platforms": [],
        "match_type": "any",
        "keywords": ["优惠", "优惠券", "满减", "便宜点", "有没有活动", "折扣", "降价"],
        "priority": 80,
        "reply": "现在店铺有满 300 减 50 的活动，结算页会自动抵扣～ 另外关注店铺可领 10 元无门槛券，叠加更划算哦！",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "发票开具",
        "platforms": ["tmall", "taobao", "jd", "pdd"],
        "match_type": "any",
        "keywords": ["发票", "开票", "税号", "专票", "普票"],
        "priority": 78,
        "reply": "可以开电子发票的～ 请提供「抬头 + 税号」，专票请额外提供开户行与账号，我们会在 3 个工作日内发送到您的邮箱。",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "抖音直播间专属",
        "platforms": ["douyin"],
        "match_type": "any",
        "keywords": ["直播间", "小黄车", "主播", "链接在哪", "怎么买"],
        "priority": 76,
        "reply": "亲，直播间的商品点左下角小黄车就能看到啦～ 拍下后备注「直播间」我们再送一份小样 🎁",
        "work_hours": "",
        "is_fallback": 0,
    },
    {
        "name": "通用欢迎语（兜底）",
        "platforms": [],
        "match_type": "fallback",
        "keywords": [],
        "priority": 1,
        "reply": "亲，欢迎光临 {店铺}～ 我是客服{客服名}，有什么可以帮您？回复「物流 / 尺码 / 退换 / 发票」可以快速获取答案哦！",
        "work_hours": "00:00-23:59",
        "is_fallback": 1,
    },
]

SEED_TEMPLATES = [
    ("售前", "首次咨询欢迎语", "亲，欢迎光临 {店铺}～ 我是客服{客服名}，这款 {商品名} 现在有现货，今天下单当天发出哦！", ["欢迎", "售前"]),
    ("售前", "尺码引导", "麻烦告诉我身高体重，我帮您推荐最合适的码数～", ["尺码", "服装"]),
    ("售前", "库存确认", "亲这款目前有现货，拍下即可安排发出，颜色尺码都齐全哦。", ["库存"]),
    ("售前", "推荐加购", "买两件可以走店铺满减，比单买省 30 元，需要我帮您搭配一下吗？", ["连带", "满减"]),
    ("物流", "发货时效", "我们承诺 48 小时内发货，实际通常 12 小时内就会揽收，节假日顺延。", ["发货"]),
    ("物流", "物流查询", "您的包裹目前 {物流状态}，预计 1-2 天送达，请保持电话畅通～", ["物流"]),
    ("物流", "快递异常", "我这边帮您联系快递核实，24 小时内给您答复，如果丢件我们直接补发。", ["异常", "丢件"]),
    ("售后", "七天无理由", "支持 7 天无理由退换，商品不影响二次销售即可，运费险已赠送。", ["退货"]),
    ("售后", "质量问题", "非常抱歉！麻烦拍照给我，确认后立刻补发或全额退款，运费我们承担。", ["质量", "破损"]),
    ("售后", "退款进度", "您的退款已提交，平台审核 1-3 个工作日原路退回，请留意账户变动。", ["退款", "进度"]),
    ("财务", "开具发票", "请提供发票抬头与税号，电子发票 3 个工作日内发送至您的邮箱。", ["发票"]),
    ("通用", "转人工", "已为您转接人工客服，请稍等片刻，{客服名}马上为您服务～", ["人工"]),
    ("通用", "结束语", "感谢您的支持，祝您生活愉快～ 后续有任何问题随时找我 😊", ["结束", "好评"]),
]

BUYER_NAMES = ["柠檬不酸", "小鹿要早睡", "阿May", "老张头", "大橘子", "苏打水", "半糖去冰",
               "一只兔子", "夜航船", "石头剪刀布", "南风知我意", "芝士就是力量"]
PRODUCTS = ["纯棉宽松短袖T恤", "轻量透气跑步鞋", "304不锈钢保温杯", "日式简约收纳架",
            "高支防晒衬衫", "静音机械键盘", "有机冷萃咖啡液", "婴儿纯棉浴巾"]
LOGISTICS = ["已揽收，等待发出", "运输中，已到达杭州转运中心", "派送中，快递员正在路上",
             "已签收", "因天气原因延迟，请耐心等待"]

QUESTIONS = {
    "物流": ["我的快递到哪了？", "什么时候发货呀", "怎么还没发货，都三天了", "能发顺丰吗", "运单号发我一下"],
    "尺码": ["175 身高 70 公斤选什么码", "这个偏大还是偏小", "我平时穿 L 码，这个选 L 可以吗"],
    "优惠": ["有优惠券吗", "能便宜点吗", "满减活动还有吗", "双十一会降价吗"],
    "发票": ["能开发票吗", "要专票，税号我发你", "发票什么时候能开出来"],
    "退换": ["不合适可以退吗", "我要换货，颜色不喜欢", "退款多久到账"],
    "质量": ["收到的时候是破损的", "少发了一件", "颜色和图片差好多"],
    "人工": ["转人工", "人工客服在吗", "我要投诉"],
    "欢迎": ["在吗", "你好", "这款还有货吗"],
}

SESSION_SEED = [
    ("s_1001", "tmall", "柠檬不酸", "纯棉宽松短袖T恤", "TM20261017008812"),
    ("s_1002", "pdd", "老张头", "304不锈钢保温杯", "PDD2026101704412"),
    ("s_1003", "jd", "阿May", "静音机械键盘", "JD2026101700331"),
    ("s_1004", "douyin", "半糖去冰", "轻量透气跑步鞋", "DY2026101700775"),
    ("s_1005", "taobao", "南风知我意", "日式简约收纳架", "TB2026101700912"),
    ("s_1006", "tmall", "大橘子", "高支防晒衬衫", "TM20261017008877"),
    ("s_1007", "tmall", "石头剪刀布", "有机冷萃咖啡液", "TM20261017008899"),
    ("s_1008", "pdd", "夜航船", "婴儿纯棉浴巾", "PDD2026101704421"),
    ("s_1009", "taobao", "一只兔子", "静音机械键盘", "TB2026101700915"),
]


def now_str(ts=None):
    return datetime.datetime.fromtimestamp(ts or datetime.datetime.now().timestamp()).strftime("%Y-%m-%d %H:%M:%S")


def seed_history(con):
    """生成过去 6 天的历史会话与日志，让趋势图首次打开就有真实形态。
    这些会话标记为 closed=1，不会出现在会话中心。"""
    import random
    rules = [dict(r) for r in con.execute("SELECT id,name,reply FROM rules WHERE is_fallback=0")]
    if not rules:
        return
    base = datetime.datetime.now()
    for day_off in range(6, 0, -1):
        day = (base - datetime.timedelta(days=day_off)).replace(hour=0, minute=0, second=0, microsecond=0)
        n = random.randint(3, 9)
        for k in range(n):
            ts = day + datetime.timedelta(hours=random.randint(9, 22), minutes=random.randint(0, 59))
            pid, pname = random.choice([(p[0], p[1]) for p in PLATFORMS])
            buyer = random.choice(BUYER_NAMES)
            product = random.choice(PRODUCTS)
            sid = "h_%s_%d" % (day.strftime("%m%d"), k)
            order = "%s%012d" % ("H", random.randint(10 ** 10, 10 ** 11))
            cat = random.choice(list(QUESTIONS.keys()))
            q = random.choice(QUESTIONS[cat])
            rule = random.choice(rules)
            reply = rule["reply"]
            for var, val in (("{昵称}", buyer), ("{店铺}", "振远优选旗舰店"), ("{客服名}", "小远"),
                             ("{商品名}", product), ("{订单号}", order),
                             ("{物流状态}", random.choice(LOGISTICS))):
                reply = reply.replace(var, val)
            con.execute(
                "INSERT OR IGNORE INTO sessions(id,platform,buyer,product,order_no,last_message,"
                "last_time,unread,status,closed) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (sid, pid, buyer, product, order, "我：" + reply.split("\n")[0][:40],
                 now_str(ts.timestamp()), 0, "auto", 1),
            )
            con.execute(
                "INSERT INTO messages(session_id,role,content,platform,ts,source) VALUES(?,?,?,?,?,?)",
                (sid, "buyer", q, pid, now_str(ts.timestamp()), "buyer"),
            )
            con.execute(
                "INSERT INTO messages(session_id,role,content,platform,ts,source) VALUES(?,?,?,?,?,?)",
                (sid, "agent", reply, pid, now_str((ts + datetime.timedelta(seconds=6)).timestamp()), "auto"),
            )
            con.execute(
                "INSERT INTO logs(ts,platform,buyer,session_id,question,rule_id,rule_name,reply,mode,latency_ms)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (now_str(ts.timestamp()), pid, buyer, sid, q, rule["id"], rule["name"],
                 reply, "auto", random.randint(8, 60)),
            )
            con.execute("UPDATE rules SET hits=hits+1 WHERE id=?", (rule["id"],))


def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=8000")
    return con


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


SCHEMA = """
CREATE TABLE IF NOT EXISTS platforms(
    id TEXT PRIMARY KEY, name TEXT, color TEXT, short TEXT,
    api_name TEXT, api_note TEXT,
    enabled INTEGER DEFAULT 0, mode TEXT DEFAULT 'demo',
    app_key TEXT DEFAULT '', app_secret TEXT DEFAULT '',
    shop TEXT DEFAULT '', status TEXT DEFAULT 'offline',
    today_sessions INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rules(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, platforms TEXT DEFAULT '[]',
    match_type TEXT DEFAULT 'any', keywords TEXT DEFAULT '[]',
    priority INTEGER DEFAULT 50, reply TEXT DEFAULT '',
    work_hours TEXT DEFAULT '', enabled INTEGER DEFAULT 1,
    is_fallback INTEGER DEFAULT 0, hits INTEGER DEFAULT 0,
    note TEXT DEFAULT '', created_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS templates(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT, title TEXT, content TEXT, tags TEXT DEFAULT '[]',
    uses INTEGER DEFAULT 0, created_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions(
    id TEXT PRIMARY KEY, platform TEXT, buyer TEXT,
    product TEXT DEFAULT '', order_no TEXT DEFAULT '',
    last_message TEXT DEFAULT '', last_time TEXT DEFAULT '',
    unread INTEGER DEFAULT 0, status TEXT DEFAULT 'auto',
    closed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT, role TEXT, content TEXT,
    platform TEXT, ts TEXT, source TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS logs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, platform TEXT, buyer TEXT, session_id TEXT,
    question TEXT, rule_id INTEGER, rule_name TEXT,
    reply TEXT, mode TEXT, latency_ms INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def seed_replies(con):
    """为预置会话生成一轮自动回复，保证首屏统计不是空的。"""
    import engine
    rules = [dict(r) for r in con.execute("SELECT * FROM rules ORDER BY priority DESC, id ASC")]
    pm = {p[0]: p[1] for p in PLATFORMS}
    settings = dict(DEFAULT_SETTINGS)
    for row in con.execute("SELECT * FROM sessions WHERE closed=0").fetchall():
        s = dict(row)
        last = con.execute(
            "SELECT content, ts FROM messages WHERE session_id=? AND role='buyer' ORDER BY id DESC LIMIT 1",
            (s["id"],)).fetchone()
        if not last:
            continue
        try:
            rule, hits = engine.match_rule(last["content"], s["platform"], rules, True)
        except Exception:
            continue
        if not rule:
            continue
        ctx = engine.build_context(s, settings, pm.get(s["platform"], s["platform"]))
        reply = engine.build_reply(rule, ctx, settings)
        ts = now_str()
        con.execute("UPDATE sessions SET last_message=?, last_time=? WHERE id=?",
                    ("我：" + reply.split("\n")[0][:40], ts, s["id"]))
        con.execute("INSERT INTO messages(session_id,role,content,platform,ts,source) VALUES(?,?,?,?,?,?)",
                    (s["id"], "agent", reply, s["platform"], ts, "auto"))
        con.execute("UPDATE rules SET hits=hits+1 WHERE id=?", (rule["id"],))
        con.execute(
            "INSERT INTO logs(ts,platform,buyer,session_id,question,rule_id,rule_name,reply,mode,latency_ms)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ts, s["platform"], s["buyer"], s["id"], last["content"], rule["id"], rule["name"],
             reply, "auto", 8))


def init_db(force_seed=False):
    con = connect()
    con.executescript(SCHEMA)
    cur = con.execute("SELECT COUNT(*) c FROM platforms")
    if force_seed or cur.fetchone()["c"] == 0:
        for pid, name, color, short, api_name, api_note in PLATFORMS:
            con.execute(
                "INSERT OR REPLACE INTO platforms(id,name,color,short,api_name,api_note,"
                "enabled,mode,status) VALUES(?,?,?,?,?,?,?,?,?)",
                (pid, name, color, short, api_name, api_note,
                 1 if pid in ("tmall", "pdd") else 0, "demo",
                 "online" if pid in ("tmall", "pdd") else "offline"),
            )
        ts = now_str()
        for r in SEED_RULES:
            con.execute(
                "INSERT INTO rules(name,platforms,match_type,keywords,priority,reply,"
                "work_hours,enabled,is_fallback,note,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (r["name"], json.dumps(r["platforms"], ensure_ascii=False), r["match_type"],
                 json.dumps(r["keywords"], ensure_ascii=False), r["priority"], r["reply"],
                 r["work_hours"], 1, r["is_fallback"], r.get("note", ""), ts, ts),
            )
        for cat, title, content, tags in SEED_TEMPLATES:
            con.execute(
                "INSERT INTO templates(category,title,content,tags,uses,created_at) VALUES(?,?,?,?,?,?)",
                (cat, title, content, json.dumps(tags, ensure_ascii=False), 0, ts),
            )
        for key, val in DEFAULT_SETTINGS.items():
            con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                        (key, json.dumps(val, ensure_ascii=False)))

        # 演示会话（保证首次进入页面不是空壳）
        base = datetime.datetime.now()
        openers = ["在吗，想问下这款还有货吗", "什么时候发货呀", "有优惠券吗",
                   "尺码怎么选呀", "能开发票吗", "支持七天无理由退货吗",
                   "收到的时候有破损", "转人工"]
        for idx, (sid, plat, buyer, product, order_no) in enumerate(SESSION_SEED):
            t = base - datetime.timedelta(minutes=18 - idx * 2)
            con.execute(
                "INSERT OR REPLACE INTO sessions(id,platform,buyer,product,order_no,"
                "last_message,last_time,unread,status) VALUES(?,?,?,?,?,?,?,?,?)",
                (sid, plat, buyer, product, order_no, "", now_str(t.timestamp()), 1, "auto"),
            )
            con.execute(
                "INSERT INTO messages(session_id,role,content,platform,ts,source) VALUES(?,?,?,?,?,?)",
                (sid, "buyer", openers[idx % len(openers)], plat, now_str(t.timestamp()), "buyer"),
            )
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('seeded','1')")
        seed_history(con)
        seed_replies(con)
    else:
        for key, val in DEFAULT_SETTINGS.items():
            con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",
                        (key, json.dumps(val, ensure_ascii=False)))
    con.commit()
    con.close()


def get_settings():
    con = connect()
    data = {r["key"]: json.loads(r["value"]) for r in con.execute("SELECT key,value FROM settings")}
    con.close()
    merged = dict(DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def set_settings(patch: dict):
    con = connect()
    for k, v in patch.items():
        con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                    (k, json.dumps(v, ensure_ascii=False)))
    con.commit()
    con.close()
