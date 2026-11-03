# -*- coding: utf-8 -*-
"""自检脚本：规则引擎单测 + HTTP 接口冒烟测试。

用法：
    python selftest.py            # 引擎单测 + 若服务在跑则做接口测试
    python selftest.py --api 8799 # 指定端口做接口测试
"""
import sys
import json
import urllib.request
import urllib.error

import db
import engine

PASS, FAIL = [], []


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("  [PASS] %s" % name)
    else:
        FAIL.append(name + ("  " + str(extra) if extra else ""))
        print("  [FAIL] %s %s" % (name, extra))


def engine_tests():
    print("\n[1] 规则引擎")
    db.init_db()
    con = db.connect()
    rules = [dict(r) for r in con.execute("SELECT * FROM rules ORDER BY priority DESC, id ASC")]
    con.close()

    r, h = engine.match_rule("我的快递到哪了", "taobao", rules)
    check("物流类命中", r and r["name"] == "物流查询", r["name"] if r else None)

    r, h = engine.match_rule("转人工", "taobao", rules)
    check("高优先级优先（转人工 vs 兜底）", r and r["name"] == "转人工优先", r["name"] if r else None)

    r, h = engine.match_rule("完全无关的一句话", "taobao", rules)
    check("无匹配时落到兜底", r and r["is_fallback"] == 1, r["name"] if r else None)

    r, h = engine.match_rule("完全无关的一句话", "taobao", rules, allow_fallback=False)
    check("关闭兜底后返回空", r is None)

    # 平台隔离：抖音专属规则不应在淘宝命中
    r, h = engine.match_rule("直播间小黄车在哪", "taobao", rules)
    check("平台隔离生效", not (r and r["name"] == "抖音直播间专属"), r["name"] if r else None)
    r, h = engine.match_rule("直播间小黄车在哪", "douyin", rules)
    check("对应平台可命中", r and r["name"] == "抖音直播间专属", r["name"] if r else None)

    check("跨零点时段 23:00-08:00 在上午不生效", engine.within_hours("23:00-08:00") is False)
    check("空时段表示全天", engine.within_hours("") is True)

    out = engine.render("亲{昵称}，{商品名}已发出，单号{订单号}", {
        "buyer": "小鹿", "product": "T恤", "order_no": "TM123"})
    check("变量渲染", out == "亲小鹿，T恤已发出，单号TM123", out)

    out = engine.render("未知变量{不存在的}", {"buyer": "x"})
    check("未知变量原样保留", out == "未知变量{不存在的}", out)

    blocked, w = engine.filter_sensitive("给您差评处理", ["差评", "投诉"])
    check("敏感词拦截", blocked and w == "差评")

    # 正则规则临时插入内存测试
    reg = {"id": 999, "name": "正则测试", "platforms": [], "match_type": "regex",
           "keywords": ["发货|寄出|什么时候发"], "priority": 200, "reply": "x",
           "work_hours": "", "enabled": 1, "is_fallback": 0}
    r, h = engine.match_rule("这件什么时候发呀", "jd", rules + [reg])
    check("正则匹配", r and r["name"] == "正则测试", r["name"] if r else None)

    ex = {"id": 998, "name": "精确", "platforms": [], "match_type": "exact",
          "keywords": ["在吗"], "priority": 300, "reply": "x", "work_hours": "",
          "enabled": 1, "is_fallback": 0}
    check("完全匹配不误伤长句", engine.match_rule("在吗，这款有货吗", "jd", rules + [ex])[0]["name"] != "精确")
    check("完全匹配命中整句", engine.match_rule("在吗", "jd", rules + [ex])[0]["name"] == "精确")


def api_tests(port):
    print("\n[2] HTTP 接口 (:%d)" % port)
    base = "http://127.0.0.1:%d" % port

    def req(path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(base + path, data=data, method=method,
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        b = req("/api/bootstrap")
        check("bootstrap 返回平台与规则", len(b["platforms"]) == 5 and len(b["rules"]) >= 8)
        check("bootstrap 含统计", "trend" in b["stats"] and len(b["stats"]["trend"]) == 7)

        t = req("/api/test", "POST", {"text": "我要退货", "platform": "tmall"})
        check("测试接口命中退换货", t["matched"] and t["rule_name"] == "退换货政策", t.get("rule_name"))
        check("测试接口已渲染变量", "{店铺}" not in t["reply"] and "{客服名}" not in t["reply"], t["reply"][:40])

        created = req("/api/rules", "POST", {"name": "自检临时规则", "match_type": "any",
                                            "keywords": ["自检词"], "priority": 66,
                                            "reply": "自检回复", "platforms": [], "enabled": 1})
        rid = created["id"]
        check("新建规则", any(r["name"] == "自检临时规则" for r in created["items"]))

        upd = req("/api/rules/%d" % rid, "PUT", {"name": "自检临时规则2", "match_type": "any",
                                                 "keywords": ["自检词2"], "priority": 67,
                                                 "reply": "自检回复2", "platforms": ["jd"]})
        check("编辑规则", any(r["name"] == "自检临时规则2" and r["priority"] == 67 for r in upd["items"]))

        tg = req("/api/rules/%d/toggle" % rid, "POST", {})
        check("启停开关", tg["enabled"] == 0)

        try:
            req("/api/rules", "POST", {"name": "空关键词", "match_type": "any", "keywords": [], "reply": "x"})
            check("空关键词被拒绝", False)
        except urllib.error.HTTPError as e:
            check("空关键词被拒绝", e.code == 400)

        req("/api/rules/%d" % rid, "DELETE")
        after = req("/api/rules")
        check("删除规则", not any(r["name"] == "自检临时规则2" for r in after["items"]))

        sim = req("/api/simulate", "POST", {})
        check("模拟咨询返回结果", sim.get("ok") is True and "session_id" in sim)

        logs = req("/api/logs?page=1&size=5")
        check("日志分页", "items" in logs and "total" in logs)

        feed = req("/api/feed?since=0")
        check("实时流游标", "cursor" in feed and isinstance(feed["logs"], list))
    except Exception as exc:
        check("接口连通", False, exc)


if __name__ == "__main__":
    port = None
    if "--api" in sys.argv:
        port = int(sys.argv[sys.argv.index("--api") + 1])
    else:
        port = 8799

    engine_tests()
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/api/bootstrap" % port, timeout=2)
        api_tests(port)
    except Exception:
        print("\n[2] 跳过接口测试：端口 %d 上没有运行中的服务" % port)

    print("\n" + "=" * 46)
    print("  通过 %d 项 / 失败 %d 项" % (len(PASS), len(FAIL)))
    for f in FAIL:
        print("  - " + f)
    print("=" * 46)
    sys.exit(1 if FAIL else 0)
