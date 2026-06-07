import json
import re

from tools.xhs_ugc import search_xhs_public_notes


TIME_HINTS = {
    "morning": ["早茶", "早餐", "上午", "早上", "brunch"],
    "lunch": ["午餐", "中午", "午饭", "正餐", "本地菜"],
    "afternoon": ["下午茶", "咖啡", "甜品", "避暑", "休息", "拍照"],
    "dinner": ["晚餐", "晚上", "夜市", "火锅", "烧烤", "酒吧", "夜景"],
}

AVOID_HINTS = ["避雷", "踩雷", "排队", "人多", "不好吃", "贵", "绕路"]
POSITIVE_HINTS = ["推荐", "必去", "好吃", "出片", "本地人", "性价比", "值得", "小众"]


def build_city_guide(city: str, preferences: list[str] | None = None, limit: int = 6) -> dict:
    """Turn public XHS/search snippets into planning hints.

    The function intentionally uses search-visible summaries only. It does not
    login, bypass anti-bot flows, or scrape private content.
    """
    if not city:
        return {}

    prefs = " ".join(preferences or [])
    queries = _build_guide_queries(city, preferences or [])
    if prefs:
        queries.insert(0, f"{city} {prefs} 小红书 攻略 避雷 推荐 排队 时间安排")

    items = []
    seen = set()
    try:
        for query in queries[:2]:
            raw = search_xhs_public_notes.invoke({"query": query, "limit": max(3, limit // 2)})
            batch = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(batch, list):
                continue
            for item in batch:
                key = item.get("url") or item.get("title")
                if key and key not in seen:
                    seen.add(key)
                    items.append(item)
    except Exception:
        return {}

    if not isinstance(items, list):
        return {}

    snippets = []
    for item in items[:limit]:
        text = f"{item.get('title', '')} {item.get('content', '')}".strip()
        if text:
            snippets.append(text[:240])

    combined = " ".join(snippets)
    return {
        "source": "xhs_public_search",
        "snippets": snippets[:4],
        "hot_places": _extract_hot_places(combined)[:12],
        "time_hints": _collect_time_hints(combined),
        "avoid_keywords": _collect_keywords(combined, AVOID_HINTS),
        "positive_keywords": _collect_keywords(combined, POSITIVE_HINTS),
        "strategy": _build_strategy(combined),
    }


def _build_guide_queries(city: str, preferences: list[str]) -> list[str]:
    pref_text = " ".join(preferences)
    queries = [
        f"{city} 小红书 本地人推荐 宝藏小店 路线 收藏",
        f"{city} 小红书 避雷 排队 少排队 探店",
        f"{city} 小红书 周末 攻略 小众 好玩 好吃",
    ]
    if any(pref in preferences for pref in ["美食", "咖啡", "探店", "休闲"]):
        queries.append(f"{city} {pref_text} 小红书 好吃 人均 控排队 宝藏餐厅")
    if any(pref in preferences for pref in ["游戏", "娱乐", "夜景", "热闹"]):
        queries.append(f"{city} {pref_text} 小红书 晚上 好玩 livehouse 电竞 夜景")
    if any(pref in preferences for pref in ["看展", "拍照", "历史"]):
        queries.append(f"{city} {pref_text} 小红书 展览 拍照 打卡 小众")
    if any(pref in preferences for pref in ["爬山", "户外", "自然"]):
        queries.append(f"{city} {pref_text} 小红书 徒步 爬山 公园 路线")
    return queries


def _extract_hot_places(text: str) -> list[str]:
    candidates = []
    patterns = [
        r"[「【《]([^」】》]{2,24})[」】》]",
        r"([\u4e00-\u9fa5A-Za-z0-9·&' -]{2,24})(?:店|馆|园|城|街|塔|山|湖|寺|吧|剧场|Livehouse|livehouse)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            name = re.sub(r"\s+", " ", match).strip(" -:：，,。")
            if len(name) < 2:
                continue
            if any(bad in name for bad in ["攻略", "推荐", "避雷", "排队", "时间", "路线", "小红书"]):
                continue
            if name not in candidates:
                candidates.append(name)
    return candidates


def _collect_time_hints(text: str) -> dict:
    result = {}
    for slot, keywords in TIME_HINTS.items():
        matched = [keyword for keyword in keywords if keyword in text]
        if matched:
            result[slot] = matched[:4]
    return result


def _collect_keywords(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text][:6]


def _build_strategy(text: str) -> list[str]:
    strategy = []
    if any(word in text for word in ["排队", "人多", "火爆"]):
        strategy.append("热门餐饮避开 12:00 和 18:00 正峰，优先 11:15/13:30/17:15/19:30。")
    if any(word in text for word in ["早茶", "早餐"]):
        strategy.append("有早茶/早餐偏好时，把茶点类餐厅放在上午第一段。")
    if any(word in text for word in ["下午茶", "咖啡", "甜品"]):
        strategy.append("咖啡甜品更适合作为 14:30-16:30 的休息节点。")
    if any(word in text for word in ["夜景", "夜市", "酒吧"]):
        strategy.append("夜景和夜市安排在晚餐后，避免白天浪费夜间属性。")
    if not strategy:
        strategy.append("按景点-午餐-轻活动-下午茶-晚餐/夜间的日程骨架组织。")
    return strategy


def infer_food_time_slot(block: dict) -> str | None:
    text = f"{block.get('name', '')} {block.get('category', '')} {' '.join(block.get('tags') or [])}"
    if block.get("category") == "咖啡" or any(word in text.lower() for word in ["coffee", "咖啡", "下午茶"]):
        return "afternoon"
    if block.get("category") == "甜品":
        return "afternoon"
    if block.get("category") != "餐厅":
        return None
    if any(word in text for word in ["早茶", "早餐", "茶点"]):
        return "morning"
    if any(word in text for word in ["火锅", "烧烤", "酒吧", "夜宵", "宵夜"]):
        return "dinner"
    if re.search(r"(海底捞|火锅|烤肉|牛排|居酒屋)", text):
        return "dinner"
    return "meal"
