import json
import re

from tools.tavily import search_reviews


EVENT_KEYWORDS = ["音乐节", "演唱会", "展览", "市集", "活动", "演出", "赛事", "周末去哪"]

TRAD_TO_SIMP = str.maketrans({
    "臺": "台", "灣": "湾", "廣": "广", "東": "东", "門": "门", "龍": "龙", "馬": "马",
    "風": "风", "雲": "云", "會": "会", "體": "体", "驗": "验", "遊": "游", "戲": "戏",
    "藝": "艺", "術": "术", "館": "馆", "廣": "广", "場": "场", "區": "区", "縣": "县",
    "鄉": "乡", "鎮": "镇", "樂": "乐", "節": "节", "熱": "热", "點": "点", "線": "线",
    "預": "预", "覽": "览", "雙": "双", "開": "开", "關": "关", "覽": "览", "燈": "灯",
    "廟": "庙", "畫": "画", "劇": "剧", "兒": "儿", "親": "亲", "華": "华", "國": "国",
    "萬": "万", "與": "与", "書": "书", "車": "车", "雜": "杂", "長": "长", "廣": "广",
    "歲": "岁", "貓": "猫", "發": "发", "佈": "布", "這": "这", "個": "个", "時": "时",
    "間": "间", "請": "请", "將": "将", "來": "来", "為": "为", "還": "还", "後": "后",
    "讓": "让", "對": "对", "從": "从", "過": "过", "動": "动", "實": "实", "現": "现",
    "優": "优", "選": "选", "擇": "择", "鄰": "邻", "遠": "远", "輕": "轻", "鬆": "松",
})


def to_simplified(text: str) -> str:
    return (text or "").translate(TRAD_TO_SIMP)


def fetch_city_event_signals(city: str, time_slot: str | None, preferences: list[str] | None = None, limit: int = 4) -> list[dict]:
    """搜索近期热门活动信号。

    只返回搜索摘要，不把无坐标活动硬塞进行程，避免编造地点和时间。
    """
    if not city:
        return []

    prefs = " ".join(preferences or [])
    query = f"{city} {time_slot or '近期 周末'} 热门活动 音乐节 演出 展览 市集 {prefs} 2026"
    try:
        raw = search_reviews.invoke({"query": query})
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []

    if isinstance(data, dict) and data.get("error"):
        return []
    items = data if isinstance(data, list) else data.get("results", [])

    events = []
    for item in items:
        title = to_simplified(item.get("title", ""))
        content = to_simplified(item.get("content", ""))
        text = f"{title} {content}"
        if not any(keyword in text for keyword in EVENT_KEYWORDS):
            continue
        events.append({
            "title": title[:80],
            "url": item.get("url", ""),
            "summary": content[:180],
            "tags": [to_simplified(tag) for tag in _extract_event_tags(text)],
            "source": "public_search",
        })
        if len(events) >= limit:
            break

    return events


def _extract_event_tags(text: str) -> list[str]:
    tags = []
    for keyword in EVENT_KEYWORDS:
        if keyword in text:
            tags.append(keyword)
    date_match = re.search(r"(\d{1,2})[月./](\d{1,2})(?:日|号)?", text)
    if date_match:
        tags.append(f"{int(date_match.group(1))}月{int(date_match.group(2))}日")
    return tags[:4]
