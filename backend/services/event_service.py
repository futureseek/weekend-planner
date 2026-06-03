import json
import re
from datetime import date, timedelta
from urllib.parse import urlparse

from tools.tavily import search_reviews
from tools.xhs_ugc import search_xhs_public_notes


CURRENT_DATE = date.today()
_EVENT_CACHE: dict[tuple, list[dict]] = {}
EVENT_KEYWORDS = ["音乐节", "演唱会", "livehouse", "Livehouse", "展览", "市集", "活动", "演出", "漫展", "电竞", "派对", "周末去哪"]
YOUTH_KEYWORDS = ["小红书", "年轻人", "周末", "livehouse", "Livehouse", "音乐节", "演唱会", "市集", "漫展", "电竞", "潮流", "探店", "夜生活", "club", "酒吧"]
BAD_SOURCE_KEYWORDS = ["政府", "政务", "文旅", "旅游局", "文化和旅游", "人民政府", "官网", "官方发布"]
BAD_DOMAINS = ["gov.cn", "culture", "tourism", "hopetrip", "trip.com", "utravel", "bendibao"]
GENERIC_TITLE_KEYWORDS = [
    "最新消息",
    "时间安排",
    "活动日历",
    "活动汇总",
    "演出首页",
    "首页",
    "好去处",
    "攻略",
    "指南",
    "门票信息",
    "购票贴士",
    "观演流程",
    "推介",
    "推荐",
    "必去",
    "玩法",
    "同城活动",
    "正在售票",
]
GENERIC_URL_KEYWORDS = [
    "huodongrili",
    "yanchanghui",
    "huodong",
    "xiuxian",
]
GENERIC_CONTENT_PHRASES = [
    "民俗活动 灯会",
    "博览展会 车展",
    "休闲展览 画展",
    "体育赛事 马拉松",
    "音乐演出 演唱会|音乐节",
    "剧场演出 话剧",
]

TRAD_TO_SIMP = str.maketrans({
    "臺": "台", "灣": "湾", "廣": "广", "東": "东", "門": "门", "龍": "龙", "馬": "马",
    "風": "风", "雲": "云", "會": "会", "體": "体", "驗": "验", "遊": "游", "戲": "戏",
    "藝": "艺", "術": "术", "館": "馆", "場": "场", "區": "区", "縣": "县",
    "鄉": "乡", "鎮": "镇", "樂": "乐", "節": "节", "熱": "热", "點": "点", "線": "线",
    "預": "预", "覽": "览", "雙": "双", "開": "开", "關": "关", "燈": "灯",
    "廟": "庙", "畫": "画", "劇": "剧", "兒": "儿", "親": "亲", "華": "华", "國": "国",
    "萬": "万", "與": "与", "書": "书", "車": "车", "雜": "杂", "長": "长",
    "歲": "岁", "貓": "猫", "發": "发", "佈": "布", "這": "这", "個": "个", "時": "时",
    "間": "间", "請": "请", "將": "将", "來": "来", "為": "为", "還": "还", "後": "后",
    "讓": "让", "對": "对", "從": "从", "過": "过", "動": "动", "實": "实", "現": "现",
    "優": "优", "選": "选", "擇": "择", "鄰": "邻", "遠": "远", "輕": "轻", "鬆": "松",
    "氣": "气", "購": "购", "貼": "贴", "觀": "观", "歡": "欢", "眾": "众", "滿": "满",
    "覺": "觉", "資": "资", "訊": "讯", "錢": "钱", "價": "价", "費": "费", "準": "准",
    "黃": "黄", "綺": "绮", "專": "专", "聯": "联", "娛": "娱", "園": "园", "啟": "启",
    "灣": "湾", "峯": "峰", "裏": "里", "於": "于", "僅": "仅", "網": "网", "獨": "独",
    "辦": "办", "屆": "届", "報": "报", "帶": "带", "應": "应", "懶": "懒", "訪": "访",
})


def to_simplified(text: str) -> str:
    return (text or "").translate(TRAD_TO_SIMP)


def fetch_city_event_signals(
    city: str,
    time_slot: str | None,
    preferences: list[str] | None = None,
    limit: int = 4,
    language: str = "zh",
) -> list[dict]:
    """搜索近期热门活动。

    活动只作为用户参考资料，不硬塞进行程。结果会按用户出行起始日到结束日后一周过滤，
    并优先保留小红书/演出/市集/Livehouse/漫展等更贴近青少年兴趣的线索。
    """
    if not city:
        return []

    window_start, window_end = _event_window(time_slot)
    prefs = " ".join(preferences or [])
    cache_key = (city, time_slot or "", tuple(preferences or []), limit, language)
    if cache_key in _EVENT_CACHE:
        return [dict(item) for item in _EVENT_CACHE[cache_key]]

    period = f"{window_start.month}月{window_start.day}日到{window_end.month}月{window_end.day}日"
    year = window_start.year
    if language == "en":
        queries = [
            f"{city} {year} {period} livehouse concert festival market anime expo young people {prefs}",
            f"{city} {year} {period} recent popular events concerts markets exhibitions nightlife {prefs}",
        ]
    else:
        queries = [
            f"{city} {year} {period} 小红书 热门活动 音乐节 演出 市集 livehouse 漫展 {prefs}",
            f"{city} {year}年 {period} 年轻人 周末去哪 演出 livehouse 市集 漫展 小红书 {prefs}",
        ]

    raw_items: list[dict] = []
    for index, query in enumerate(queries):
        try:
            if index == 0:
                raw = search_xhs_public_notes.invoke({"query": query, "limit": limit * 3})
            else:
                raw = search_reviews.invoke({"query": query})
            raw_items.extend(_parse_items(raw))
        except Exception:
            continue

    events = []
    seen = set()
    for item in raw_items:
        title = to_simplified(str(item.get("title", ""))).strip()
        content = to_simplified(str(item.get("content", ""))).strip()
        url = str(item.get("url", "")).strip()
        if not title and not content:
            continue
        if not _valid_event_url(url):
            continue

        text = f"{title} {content}"
        key = _dedupe_key(title, url)
        if key in seen:
            continue
        if _is_bad_source(text, url):
            continue
        if _is_generic_event_page(title, content, url):
            continue
        if not _has_event_signal(text):
            continue
        dates = _extract_dates(text)
        if dates and not any(window_start <= item_date <= window_end for item_date in dates):
            continue

        score = _event_score(text, url, bool(dates), item.get("source", ""))
        if score <= 0:
            continue
        seen.add(key)
        summary = _compact_event_description(title, content)
        events.append({
            "title": summary[:120],
            "url": url,
            "summary": summary,
            "summary_en": _compact_event_description_en(title, content),
            "tags": _extract_event_tags(text, dates, window_start, window_end),
            "source": item.get("source", "public_search"),
            "_score": score,
        })

    events.sort(key=lambda item: item.get("_score", 0), reverse=True)
    for event in events:
        event.pop("_score", None)
    final_events = events[:limit]
    _EVENT_CACHE[cache_key] = [dict(item) for item in final_events]
    return final_events


def _parse_items(raw) -> list[dict]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and data.get("error"):
        return []
    return data if isinstance(data, list) else data.get("results", [])


def _event_window(time_slot: str | None) -> tuple[date, date]:
    start, end = _travel_dates(time_slot)
    return start, end + timedelta(days=7)


def _travel_dates(time_slot: str | None) -> tuple[date, date]:
    text = time_slot or ""
    range_match = re.search(
        r"(\d{1,2})\s*[月./]\s*(\d{1,2})(?:日|号)?\s*(?:-|－|—|–|~|～|至|到)\s*(?:(\d{1,2})\s*[月./]\s*)?(\d{1,2})(?:日|号)?",
        text,
    )
    if range_match:
        sm, sd, em, ed = range_match.groups()
        em = em or sm
        start = _safe_date(CURRENT_DATE.year, int(sm), int(sd))
        end_year = start.year if (int(em), int(ed)) >= (int(sm), int(sd)) else start.year + 1
        end = _safe_date(end_year, int(em), int(ed))
        return start, end

    single_match = re.search(r"(\d{1,2})\s*[月./]\s*(\d{1,2})(?:日|号)?", text)
    if single_match:
        travel = _safe_date(CURRENT_DATE.year, int(single_match.group(1)), int(single_match.group(2)))
        return travel, travel

    if "后天" in text:
        travel = CURRENT_DATE + timedelta(days=2)
        return travel, travel
    if "明天" in text:
        travel = CURRENT_DATE + timedelta(days=1)
        return travel, travel
    if "今天" in text or "今晚" in text:
        return CURRENT_DATE, CURRENT_DATE
    if "周末" in text or "周六" in text or "周日" in text:
        saturday = _next_weekday(5)
        sunday = saturday + timedelta(days=1)
        return saturday, sunday

    return CURRENT_DATE, CURRENT_DATE


def _safe_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        return CURRENT_DATE


def _next_weekday(target_weekday: int) -> date:
    days = (target_weekday - CURRENT_DATE.weekday()) % 7
    return CURRENT_DATE + timedelta(days=days or 7)


def _extract_dates(text: str) -> list[date]:
    dates: list[date] = []
    for match in re.finditer(r"(?:(20\d{2})\s*年)?\s*(\d{1,2})\s*[月./]\s*(\d{1,2})(?:日|号)?", text):
        year = int(match.group(1) or CURRENT_DATE.year)
        month = int(match.group(2))
        day = int(match.group(3))
        dates.append(_safe_date(year, month, day))
    for match in re.finditer(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text):
        dates.append(_safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
    return list(dict.fromkeys(dates))


def _has_event_signal(text: str) -> bool:
    return any(keyword.lower() in text.lower() for keyword in EVENT_KEYWORDS + YOUTH_KEYWORDS)


def _is_bad_source(text: str, url: str) -> bool:
    lower_url = url.lower()
    host = urlparse(url).netloc.lower()
    if any(domain in host for domain in BAD_DOMAINS):
        return True
    return any(keyword in text for keyword in BAD_SOURCE_KEYWORDS) or any(keyword in lower_url for keyword in BAD_DOMAINS)


def _valid_event_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    if len(url) > 220:
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if not host or "." not in host:
        return False
    path = parsed.path.lower()
    query = parsed.query.lower()
    if any(token in path for token in ["/search", "/s?", "/results"]):
        return False
    if "search" in query or "%e6%90%9c%e7%b4%a2" in url.lower():
        return False
    return True


def _is_generic_event_page(title: str, content: str, url: str) -> bool:
    text = f"{title} {content}"
    lower_url = url.lower()
    title_hit = any(keyword in title for keyword in GENERIC_TITLE_KEYWORDS)
    hard_generic = any(keyword in title for keyword in ["同城活动", "正在售票", "活动汇总", "活动日历", "首页"])
    phrase_hit = any(phrase in text for phrase in GENERIC_CONTENT_PHRASES)
    url_hit = any(keyword in lower_url for keyword in GENERIC_URL_KEYWORDS)
    direct_signal = _has_specific_event_signal(text) and any(
        keyword.lower() in text.lower()
        for keyword in ["livehouse", "音乐节", "演唱会", "漫展", "市集", "展览", "电竞", "派对", "剧场"]
    )
    if hard_generic:
        return True
    if phrase_hit:
        return True
    if title_hit and url_hit:
        return True
    if title_hit and not direct_signal:
        return True
    return False


def _event_score(text: str, url: str, has_date: bool, source: str) -> int:
    score = 0
    lower_url = url.lower()
    lower_text = text.lower()
    if "xiaohongshu" in lower_url or "xhs" in lower_url or "小红书" in text or source == "xhs_search":
        score += 5
    if has_date:
        score += 4
    score += sum(1 for keyword in YOUTH_KEYWORDS if keyword.lower() in lower_text)
    score += min(4, sum(1 for keyword in EVENT_KEYWORDS if keyword.lower() in lower_text))
    return score


def _compact_summary(content: str, title: str) -> str:
    return _compact_event_description(title, content)[:180]


def _compact_event_description(title: str, content: str) -> str:
    title = _clean_event_text(title)
    content = _clean_event_text(content)
    title = _short_event_title(title)
    detail = _event_detail_sentence(content, title)
    if title and detail:
        candidate = f"{title}：{detail}"
    else:
        candidate = title or detail or "热门活动"
    return _trim_event_summary(re.sub(r"\s+", " ", candidate).strip(" ：:，,。"), 118)


def _compact_event_description_en(title: str, content: str) -> str:
    title = _short_event_title(_clean_event_text(title))
    content = _clean_event_text(content)
    kind = _event_kind_label(f"{title} {content}", english=True)
    detail = _event_detail_sentence(content, title)
    if title and detail:
        return _trim_event_summary(f"{title}: {kind}; {detail}", 118)
    if title:
        return _trim_event_summary(f"{title}: {kind}", 118)
    return _trim_event_summary(f"Popular local event: {detail or kind}", 118)


def _clean_event_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"#+\s*", "", text)
    text = re.sub(r"[-_]{3,}", " ", text)
    for phrase in GENERIC_CONTENT_PHRASES:
        text = text.replace(phrase, "")
    text = re.sub(r"(民俗活动|灯会|庙会|光影演出|灯光秀|喷泉|商场市集|文创|夜市|博览展会|车展|漫展|休闲展览|画展|艺术展|音乐演出|演唱会\|音乐节|剧场演出|话剧|儿童剧|体育赛事|马拉松)[、,， ]*", "", text)
    return text.strip(" ：:，,。")


def _short_event_title(title: str) -> str:
    title = re.sub(r"\[[^\]]{1,18}\]", "", title)
    title = re.sub(r"【[^】]{1,18}】", "", title)
    title = re.sub(r"#+\s*", "", title)
    title = re.sub(r"\s+", " ", title).strip(" ：:，,。")
    if len(title) <= 44:
        return title
    for sep in [" ----- ", "-----", " - ", "｜", "|", "_", "：", ":"]:
        if sep in title:
            title = title.split(sep, 1)[0].strip()
            break
    return title[:44].strip(" ：:，,。")


def _event_detail_sentence(content: str, title: str = "") -> str:
    text = content.replace(title, "").strip() if title else content
    text = re.sub(r"来源[:：]\s*[^，。；; ]+", "", text)
    text = re.sub(r"热门搜索[:：].*", "", text)
    sentences = [item.strip(" ：:，,。") for item in re.split(r"[。；;\n]", text) if item.strip()]
    scored = []
    for sentence in sentences:
        if len(sentence) < 8:
            continue
        if any(phrase in sentence for phrase in GENERIC_CONTENT_PHRASES):
            continue
        score = 0
        score += 3 if re.search(r"\d{1,2}\s*[月./]\s*\d{1,2}|20\d{2}", sentence) else 0
        score += 2 if any(word in sentence for word in ["时间", "日期", "地点", "场馆", "票", "价格", "演出", "市集", "展览", "livehouse", "Livehouse"]) else 0
        score += sum(1 for keyword in YOUTH_KEYWORDS if keyword.lower() in sentence.lower())
        scored.append((score, sentence))
    if not scored:
        return ""
    scored.sort(key=lambda item: (item[0], -len(item[1])), reverse=True)
    return _trim_event_summary(scored[0][1], 76)


def _has_specific_event_signal(text: str) -> bool:
    if re.search(r"\d{1,2}\s*[月./]\s*\d{1,2}|20\d{2}[-/]\d{1,2}[-/]\d{1,2}", text):
        return True
    return bool(re.search(r"(时间|日期|地点|场馆|票价|开演|演出)[:：]", text))


def _trim_event_summary(text: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", text or "").strip(" ：:，,。")
    if len(value) <= limit:
        return value
    cut = value[:limit]
    for sep in ["。", "；", ";", "，", ",", " "]:
        idx = cut.rfind(sep)
        if idx >= max(48, limit // 2):
            return cut[:idx].strip(" ：:，,。")
    return cut.rstrip(" ：:，,。") + "..."


def _event_kind_label(text: str, english: bool = False) -> str:
    lower = text.lower()
    mapping = [
        (("livehouse", "演唱会", "音乐节", "演出"), ("live music", "音乐演出")),
        (("漫展", "动漫", "comic"), ("anime/comic event", "漫展活动")),
        (("市集", "夜市"), ("market/fair", "市集")),
        (("电竞", "游戏"), ("gaming event", "游戏电竞")),
        (("展览", "展会", "艺术展"), ("exhibition", "展览")),
        (("派对", "club", "酒吧"), ("nightlife event", "夜生活")),
    ]
    for keywords, labels in mapping:
        if any(keyword.lower() in lower for keyword in keywords):
            return labels[0] if english else labels[1]
    return "local event" if english else "本地活动"


def _dedupe_key(title: str, url: str) -> str:
    return (url or re.sub(r"\s+", "", title.lower()))[:120]


def _extract_event_tags(text: str, dates: list[date], window_start: date, window_end: date) -> list[str]:
    tags = []
    for keyword in EVENT_KEYWORDS:
        if keyword.lower() in text.lower():
            tags.append(keyword)
    if dates:
        tags.append("时间匹配")
    tags.append(f"{window_start.month}.{window_start.day}-{window_end.month}.{window_end.day}")
    return list(dict.fromkeys(tags))[:4]
