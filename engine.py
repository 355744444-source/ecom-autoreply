# -*- coding: utf-8 -*-
"""规则引擎：关键词匹配、优先级排序、生效时段、变量渲染、敏感词过滤。"""
import re
import json
import random
import datetime

MATCH_TYPES = {
    "any": "包含任一关键词",
    "all": "包含全部关键词",
    "exact": "完全匹配",
    "regex": "正则表达式",
    "fallback": "兜底（无关键词）",
}

# 变量：中文主名 + 英文别名
VAR_MAP = {
    "昵称": "buyer", "nick": "buyer",
    "店铺": "shop", "shop": "shop",
    "客服名": "agent", "agent": "agent",
    "平台": "platform_name", "platform": "platform_name",
    "商品名": "product", "product": "product",
    "订单号": "order_no", "order": "order_no",
    "物流状态": "logistics", "logistics": "logistics",
    "时间": "time", "time": "time",
    "日期": "date", "date": "date",
}

VAR_HINTS = ["{昵称}", "{店铺}", "{商品名}", "{订单号}", "{物流状态}", "{平台}", "{时间}", "{客服名}"]


def within_hours(spec: str, now=None) -> bool:
    """支持 '08:00-23:00' 与跨零点 '23:00-08:00'；空串表示全天生效。"""
    if not spec or "-" not in spec:
        return True
    now = now or datetime.datetime.now()
    try:
        start_s, end_s = [x.strip() for x in spec.split("-", 1)]
        sh, sm = [int(x) for x in start_s.split(":")]
        eh, em = [int(x) for x in end_s.split(":")]
    except Exception:
        return True
    cur = now.hour * 60 + now.minute
    start, end = sh * 60 + sm, eh * 60 + em
    if start == end:
        return True
    if start < end:
        return start <= cur <= end
    return cur >= start or cur <= end


def render(template: str, ctx: dict) -> str:
    if not template:
        return ""
    def _sub(m):
        key = m.group(1).strip()
        field = VAR_MAP.get(key)
        if not field:
            return m.group(0)
        val = ctx.get(field)
        return str(val) if val not in (None, "") else "—"
    return re.sub(r"\{([^{}]+)\}", _sub, template)


def build_context(session: dict, settings: dict, platform_name: str) -> dict:
    now = datetime.datetime.now()
    return {
        "buyer": session.get("buyer") or "亲",
        "shop": settings.get("shop_name") or "本店",
        "agent": settings.get("agent_name") or "客服",
        "platform_name": platform_name,
        "product": session.get("product") or "该商品",
        "order_no": session.get("order_no") or "—",
        "logistics": random.choice(["运输中", "已到达转运中心", "派送中"]),
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
    }


def _rule_applies(rule: dict, platform: str) -> bool:
    if not rule.get("enabled", 1):
        return False
    plats = rule.get("platforms") or []
    if isinstance(plats, str):
        try:
            plats = json.loads(plats)
        except Exception:
            plats = []
    if plats and platform not in plats:
        return False
    return within_hours(rule.get("work_hours") or "")


def _keywords(rule: dict):
    kws = rule.get("keywords") or []
    if isinstance(kws, str):
        try:
            kws = json.loads(kws)
        except Exception:
            kws = [k for k in re.split(r"[,，\n]", kws) if k.strip()]
    return [str(k).strip() for k in kws if str(k).strip()]


def match_rule(text: str, platform: str, rules: list, allow_fallback=True):
    """返回 (rule, matched_keywords)；未命中返回 (None, [])。"""
    t = (text or "").strip()
    low = t.lower()
    candidates = []
    fallback = None

    for rule in rules:
        if not _rule_applies(rule, platform):
            continue
        mt = rule.get("match_type") or "any"
        if mt == "fallback" or rule.get("is_fallback"):
            if allow_fallback and fallback is None:
                fallback = rule
            continue

        kws = _keywords(rule)
        hit = []
        if mt == "regex":
            pattern = rule.get("pattern") or ""
            if not pattern and kws:
                pattern = kws[0]
            try:
                if pattern and re.search(pattern, t, re.I):
                    m = re.search(pattern, t, re.I)
                    hit = [m.group(0)] if m and m.group(0) else [pattern]
                    candidates.append((rule, hit))
            except re.error:
                continue
        elif mt == "exact":
            for k in kws:
                if low == k.lower():
                    hit.append(k)
            if hit:
                candidates.append((rule, hit))
        elif mt == "all":
            if kws and all(k.lower() in low for k in kws):
                candidates.append((rule, kws))
        else:  # any
            for k in kws:
                if k.lower() in low:
                    hit.append(k)
            if hit:
                candidates.append((rule, hit))

    if candidates:
        candidates.sort(key=lambda x: (-int(x[0].get("priority") or 0), x[0].get("id") or 0))
        return candidates[0]

    # 长关键词加权：兜底前先看是否有更长的命中（避免「人工」被「人工客服」抢走的情况已由 priority 处理）
    if fallback:
        return fallback, []
    return None, []


def filter_sensitive(text: str, words: list):
    """返回 (是否命中, 命中的词)"""
    for w in words or []:
        if w and w in (text or ""):
            return True, w
    return False, ""


def build_reply(rule: dict, ctx: dict, settings: dict) -> str:
    body = render(rule.get("reply") or "", ctx)
    if settings.get("append_signature") and settings.get("signature"):
        sign = render(settings["signature"], ctx)
        if sign and sign not in body:
            body = body.rstrip() + "\n" + sign
    return body


def test_match(text: str, platform: str, rules: list, session: dict, settings: dict, platform_name=""):
    """规则测试器：返回命中详情，供前端展示。"""
    rule, hits = match_rule(text, platform, rules, allow_fallback=bool(settings.get("fallback_enabled", True)))
    if not rule:
        return {"matched": False, "reason": "没有规则命中，且兜底回复已关闭"}
    ctx = build_context(session or {}, settings, platform_name or platform)
    reply = build_reply(rule, ctx, settings)
    blocked, word = filter_sensitive(reply, settings.get("sensitive_words"))
    return {
        "matched": True,
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name"),
        "priority": rule.get("priority"),
        "match_type": rule.get("match_type"),
        "is_fallback": bool(rule.get("is_fallback")),
        "keywords": hits,
        "reply": reply,
        "blocked": blocked,
        "blocked_word": word,
        "latency_ms": random.randint(3, 18),
    }
