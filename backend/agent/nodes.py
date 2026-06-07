import json
import re
from datetime import date, timedelta
from langchain_core.messages import HumanMessage, AIMessage

from .state import PlannerState
from .context import build_context


CURRENT_DATE = date.today()


def _log(node: str, msg: str):
    print(f"[{node}] {msg}")


INTENT_PROMPT = """你是 Roam 的快速意图解析器。只抽字段，不做路线规划，不解释。

当前已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

用户最新消息：{message}

请严格返回 JSON，不要输出 Markdown 或额外解释：
{{
  "intent": "plan" 或 "modify" 或 "chat",
  "location": "城市或区域；没提到则为 null",
  "budget": 总预算数字，整数；没提到则为 null,
  "preferences": ["美食", "咖啡", "看展", "自然", "购物", "亲子", "夜景", "探店", "拍照", "历史", "热闹", "爬山", "户外", "游戏", "运动", "娱乐"]；没提到则为 null,
  "people_count": 人数整数；没提到则为 null,
  "time_slot": "时间描述，如 6月1日-6月3日、周六下午"；没提到则为 null,
  "force_generate": true 或 false,
  "modify_action": null 或 "less_walking" 或 "less_queue" 或 "lower_budget" 或 "replace_poi",
  "modify_payload": null 或 {{"category": "餐厅"}}
}}

判断规则：
- 用户描述城市、日期、预算、人数、偏好时，intent=plan。
- 用户说少走路、省钱、不排队、换餐厅/咖啡/景点时，intent=modify。
- 用户明显闲聊且不包含出行需求时，intent=chat。
- “6.1-6.3，2人，预算2000，喜欢逛街和热闹的地方”应解析为时间、人数、预算、购物/热闹偏好。
- 吃喝玩乐都要时，偏好应包含美食、咖啡、购物、夜景、探店。
- 用户说直接生成、不用问、先给方案时，force_generate=true。"""

ASK_PROMPT = """你是 Roam。现在还缺少生成可执行本地路线的关键信息。

已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

缺失信息：{missing}

请最多问两个短问题，语气直接，不重复已知信息，不给推荐示例。"""

CHAT_PROMPT = """你是 Roam，专注于本地多目的地路线规划。
请用 2 句话以内回复，并引导用户给出城市/区域、时间、人数、预算、起点和偏好。"""


CITY_ALIASES = {
    "杭州": "杭州",
    "西湖": "杭州",
    "湖滨": "杭州",
    "北京": "北京",
    "上海": "上海",
    "广州": "广州",
    "深圳": "深圳",
    "成都": "成都",
    "南京": "南京",
    "苏州": "苏州",
    "重庆": "重庆",
    "武汉": "武汉",
    "西安": "西安",
    "厦门": "厦门",
    "天津": "天津",
    "长沙": "长沙",
    "青岛": "青岛",
    "大连": "大连",
    "宁波": "宁波",
    "无锡": "无锡",
    "合肥": "合肥",
    "福州": "福州",
    "南昌": "南昌",
    "济南": "济南",
    "郑州": "郑州",
    "昆明": "昆明",
    "贵阳": "贵阳",
    "南宁": "南宁",
    "海口": "海口",
    "三亚": "三亚",
    "哈尔滨": "哈尔滨",
    "沈阳": "沈阳",
    "长春": "长春",
    "大理": "大理",
    "丽江": "丽江",
    "桂林": "桂林",
    "张家界": "张家界",
    "黄山": "黄山",
    "景德镇": "景德镇",
    "泉州": "泉州",
    "扬州": "扬州",
    "洛阳": "洛阳",
    "开封": "开封",
    "威海": "威海",
    "烟台": "烟台",
    "绍兴": "绍兴",
    "嘉兴": "嘉兴",
    "温州": "温州",
    "佛山": "佛山",
    "珠海": "珠海",
    "潮州": "潮州",
    "汕头": "汕头",
    "guangzhou": "广州",
    "canton": "广州",
    "shanghai": "上海",
    "beijing": "北京",
    "shenzhen": "深圳",
    "chengdu": "成都",
    "hangzhou": "杭州",
    "xian": "西安",
    "xi'an": "西安",
    "nanjing": "南京",
    "suzhou": "苏州",
    "chongqing": "重庆",
    "wuhan": "武汉",
    "xiamen": "厦门",
    "lhasa": "拉萨",
    "kashgar": "喀什",
    "urumqi": "乌鲁木齐",
}


def _normalize_city_alias(city: str | None) -> str | None:
    if not city:
        return None
    value = city.strip()
    if not value:
        return None
    value = value.replace("市", "").strip()
    lower_value = value.lower()
    return CITY_ALIASES.get(lower_value) or CITY_ALIASES.get(value) or value

PREFERENCE_PATTERNS = [
    (("吃喝玩乐", "都要", "全都要"), ["美食", "购物", "夜景", "看展", "娱乐"]),
    (("逛街", "商场", "商圈", "买东西", "购物"), ["购物"]),
    (("热闹", "热门", "人气", "烟火气"), ["热闹", "购物", "夜景"]),
    (("吃好", "吃顿好的", "吃一顿好的", "吃点好的", "美食", "吃饭", "餐厅", "小吃", "本地菜", "好吃", "早茶", "茶点", "晚餐提档", "评分高", "特色餐厅", "高分餐厅"), ["美食"]),
    (("放松", "休闲", "轻松一下", "松弛", "不想太累", "不要太累", "不要太赶", "少赶路", "慢节奏", "按摩", "spa", "足疗", "舒服一点", "休息点", "用餐缓冲"), ["休闲", "咖啡", "娱乐"]),
    (("咖啡", "探店", "下午茶", "慢咖啡", "甜品"), ["咖啡", "探店"]),
    (("看展", "展览", "美术馆", "博物馆", "艺术"), ["看展"]),
    (("自然", "公园", "散步", "湖", "山", "湿地", "园林", "园子"), ["自然"]),
    (("爬山", "登山", "徒步", "山野", "森林", "露营", "户外", "hiking", "hike", "trekking", "outdoor"), ["爬山", "户外", "自然"]),
    (("运动", "健身", "骑行", "攀岩", "篮球", "羽毛球", "running", "cycling", "sports", "climbing"), ["运动", "户外"]),
    (("亲子", "带娃", "小朋友", "父母", "老人"), ["亲子"]),
    (("夜景", "夜游", "日落", "傍晚", "酒吧", "晚上", "夜生活", "night view", "sunset"), ["夜景"]),
    (("玩乐", "娱乐", "演出", "市集", "音乐节", "livehouse", "live"), ["娱乐", "热闹"]),
    (("打游戏", "游戏", "电竞", "电竞馆", "电玩", "电玩城", "桌游", "密室", "剧本杀", "网咖", "网吧", "game", "gaming", "esports", "arcade", "board game", "escape room"), ["游戏", "热闹"]),
    (("拍照", "出片", "打卡"), ["拍照"]),
    (("历史", "老街", "古镇", "文化"), ["历史"]),
    (("food", "eat", "restaurant", "local cuisine", "snack", "brunch", "better food", "good meal", "better dinner", "high-rated", "local food"), ["美食"]),
    (("relax", "relaxed", "chill", "spa", "massage", "not tiring", "easy pace", "easy walk", "fewer transfers"), ["休闲", "咖啡", "娱乐"]),
    (("coffee", "cafe", "brunch", "afternoon tea"), ["咖啡", "探店"]),
    (("shopping", "mall", "market", "street"), ["购物"]),
    (("museum", "gallery", "exhibition", "art"), ["看展"]),
    (("nature", "park", "lake", "mountain", "walk"), ["自然", "户外"]),
    (("photo", "photogenic", "instagram", "landmark"), ["拍照"]),
    (("history", "culture", "old town", "heritage"), ["历史"]),
    (("night", "bar", "nightlife", "lights"), ["夜景"]),
]


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _last_human_message(state: PlannerState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


def _merge_unique(items: list[str]) -> list[str]:
    result = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result


def _extract_city(message: str) -> str | None:
    lower_message = message.lower()
    for keyword, city in CITY_ALIASES.items():
        if keyword in message or keyword.lower() in lower_message:
            return city
    english_match = re.search(r"(?:in|to|visit|around)\s+([a-z][a-z'\-\s]{2,30})(?:,|\s+for|\s+with|\s+on|\s*$)", lower_message)
    if english_match:
        city_text = english_match.group(1).strip()
        if city_text in CITY_ALIASES:
            return CITY_ALIASES[city_text]
    city_match = re.search(r"([\u4e00-\u9fa5]{2,8})(?:市|城区)", message)
    if city_match:
        value = city_match.group(1)
        return CITY_ALIASES.get(value, value)

    directional_match = re.search(r"(?:在|去|到|游|玩)([\u4e00-\u9fa5]{2,10})(?:[，,、\s]|一日游|半日游|周末|旅行|旅游|玩|$)", message)
    if directional_match:
        return _clean_location_candidate(directional_match.group(1))

    leading_match = re.match(r"^([\u4e00-\u9fa5]{2,10})(?:[，,、\s]|$)", message.strip())
    if leading_match:
        return _clean_location_candidate(leading_match.group(1))
    return None


def _clean_location_candidate(candidate: str) -> str | None:
    candidate = candidate.strip("的地方城市区域周边附近")
    stop_words = {"预算", "喜欢", "想吃", "想去", "周末", "周六", "周日", "今天", "明天", "后天"}
    invalid_fragments = ["预算", "喜欢", "不想", "排队", "帮我", "请帮", "重新", "规划", "省钱", "降低"]
    if not candidate or candidate in stop_words or any(word in candidate for word in invalid_fragments):
        return None
    if candidate.startswith(("请", "帮", "想", "要")):
        return None
    for suffix in ["市", "城区"]:
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
    return candidate[:10] if len(candidate) >= 2 else None


def _extract_budget(message: str) -> int | None:
    patterns = [
        r"(?:总预算|预算|花费|控制在|不超过|以内|大概|大约|人均)\D{0,4}(\d{2,6})",
        r"(?:budget|cost|spend|under|within|around|about)\D{0,8}(\d{2,6})",
        r"(\d{2,6})\s*(?:元|块|rmb|RMB)",
        r"(?:rmb|cny|¥|\$)\s*(\d{2,6})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_people_count(message: str) -> int | None:
    structured = _extract_structured_field_any(message, ["人数", "People", "Travelers", "Travellers"])
    if structured:
        number = re.search(r"\d{1,2}", structured)
        if number:
            return int(number.group(0))
    match = re.search(r"(\d{1,2})\s*(?:人|位|个人)", message)
    if match:
        return int(match.group(1))
    en_match = re.search(r"(\d{1,2})\s*(?:people|persons|person|pax|adults?|travellers?|travelers?)", message.lower())
    if en_match:
        return int(en_match.group(1))
    if any(word in message for word in ["情侣", "两个人", "双人"]):
        return 2
    if "一家三口" in message:
        return 3
    return None


CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _chinese_number_to_int(text: str | None) -> int | None:
    if not text:
        return None
    text = text.strip()
    if text in CHINESE_NUMBERS:
        return CHINESE_NUMBERS[text]
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CHINESE_NUMBERS.get(left, 1) if left else 1
        ones = CHINESE_NUMBERS.get(right, 0) if right else 0
        value = tens * 10 + ones
        return value if 1 <= value <= 31 else None
    return None


COORD_PAIR_RE = re.compile(r"-?\d{2,3}\.\d+\s*[,，]\s*-?\d{1,2}\.\d+")
DATE_RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[./月]\s*(\d{1,2})(?:日|号)?"
    r"\s*(?:-|－|—|–|~|～|至|到)\s*"
    r"(?:(\d{1,2})\s*[./月]\s*)?(\d{1,2})(?:日|号)?(?!\d)"
)
CHINESE_DATE_RANGE_RE = re.compile(
    r"([一二两三四五六七八九十]{1,3})月([一二两三四五六七八九十]{1,3})(?:日|号)?"
    r"\s*(?:-|－|—|–|~|～|至|到)\s*"
    r"(?:([一二两三四五六七八九十]{1,3})月)?([一二两三四五六七八九十]{1,3})(?:日|号)?"
)


def _strip_coordinate_pairs(text: str) -> str:
    return COORD_PAIR_RE.sub("", text or "")


def _extract_date_range_parts(text: str) -> tuple[int, int, int, int] | None:
    clean_text = _strip_coordinate_pairs(text)
    match = DATE_RANGE_RE.search(clean_text)
    if match:
        start_month, start_day, end_month, end_day = match.groups()
        end_month = end_month or start_month
        return int(start_month), int(start_day), int(end_month), int(end_day)

    chinese_match = CHINESE_DATE_RANGE_RE.search(clean_text)
    if not chinese_match:
        return None
    start_month, start_day, end_month, end_day = chinese_match.groups()
    start_month_i = _chinese_number_to_int(start_month)
    start_day_i = _chinese_number_to_int(start_day)
    end_month_i = _chinese_number_to_int(end_month) if end_month else start_month_i
    end_day_i = _chinese_number_to_int(end_day)
    if not all([start_month_i, start_day_i, end_month_i, end_day_i]):
        return None
    return start_month_i, start_day_i, end_month_i, end_day_i


def _days_from_date_range(parts: tuple[int, int, int, int] | None) -> int | None:
    if not parts:
        return None
    start_month, start_day, end_month, end_day = parts
    try:
        start = date(CURRENT_DATE.year, start_month, start_day)
        end_year = CURRENT_DATE.year if (end_month, end_day) >= (start_month, start_day) else CURRENT_DATE.year + 1
        end = date(end_year, end_month, end_day)
        return max(1, min((end - start).days + 1, 14))
    except ValueError:
        if start_month == end_month:
            return max(1, min(end_day - start_day + 1, 14))
        return 2


def _date_label_from_range(parts: tuple[int, int, int, int] | None, day_index: int) -> str | None:
    if not parts:
        return None
    start_month, start_day, _, _ = parts
    try:
        current = date(CURRENT_DATE.year, start_month, start_day) + timedelta(days=day_index - 1)
        return f"{current.month}月{current.day}日"
    except ValueError:
        return f"{start_month}月{start_day + day_index - 1}日"


def _extract_trip_days(message: str) -> int | None:
    lower_message = message.lower()
    range_days = _days_from_date_range(_extract_date_range_parts(message))
    if range_days:
        return range_days
    digit_match = re.search(r"(?:玩|游|旅行|旅游|待|去)?\s*(\d{1,2})\s*天", message)
    if digit_match:
        return max(1, min(int(digit_match.group(1)), 14))
    english_match = re.search(r"(\d{1,2})\s*days?", lower_message)
    if english_match:
        return max(1, min(int(english_match.group(1)), 14))

    chinese_match = re.search(r"(?:玩|游|旅行|旅游|待|去)?\s*([一二两三四五六七八九十])\s*天", message)
    if chinese_match:
        return CHINESE_NUMBERS.get(chinese_match.group(1))

    if "一天" in message or "一日" in message or "one day" in lower_message:
        return 1
    if "半天" in message or "half day" in lower_message:
        return 1
    if "周末" in message or "weekend" in lower_message:
        return 2
    return None


def _format_date_label(value: date, suffix: str | None = None) -> str:
    label = f"{value.month}月{value.day}日"
    return f"{label} {suffix}" if suffix else label


def _single_date_from_text(message: str) -> str | None:
    clean = _strip_coordinate_pairs(message)
    single_match = re.search(r"(?<!\d)(\d{1,2})[./月](\d{1,2})(?:日|号)?(?!\d)", clean)
    if single_match:
        return f"{int(single_match.group(1))}月{int(single_match.group(2))}日"
    chinese_match = re.search(r"([一二两三四五六七八九十]{1,3})月([一二两三四五六七八九十]{1,3})(?:日|号)?", clean)
    if chinese_match:
        month = _chinese_number_to_int(chinese_match.group(1))
        day = _chinese_number_to_int(chinese_match.group(2))
        if month and day:
            return f"{month}月{day}日"
    return None


def _next_weekday_label(target: int, suffix: str) -> str:
    delta = (target - CURRENT_DATE.weekday()) % 7
    value = CURRENT_DATE + timedelta(days=delta or 7)
    return _format_date_label(value, suffix)


def _extract_time_slot(message: str) -> str | None:
    message = _strip_coordinate_pairs(message)
    range_parts = _extract_date_range_parts(message)
    if range_parts:
        start_month, start_day, end_month, end_day = range_parts
        return f"{int(start_month)}月{int(start_day)}日-{int(end_month)}月{int(end_day)}日"

    parts = []
    single_date = _single_date_from_text(message)
    if single_date:
        parts.append(single_date)

    days = _extract_trip_days(message)
    if days and days > 1:
        parts.append(f"{days}天")

    relative_dates = {
        "今天": _format_date_label(CURRENT_DATE, "今天"),
        "今晚": _format_date_label(CURRENT_DATE, "晚上"),
        "明天": _format_date_label(CURRENT_DATE + timedelta(days=1), "明天"),
        "明晚": _format_date_label(CURRENT_DATE + timedelta(days=1), "晚上"),
        "后天": _format_date_label(CURRENT_DATE + timedelta(days=2), "后天"),
        "本周六": _next_weekday_label(5, "周六"),
        "周六": _next_weekday_label(5, "周六"),
        "下周六": _next_weekday_label(5, "周六"),
        "本周日": _next_weekday_label(6, "周日"),
        "周日": _next_weekday_label(6, "周日"),
        "下周日": _next_weekday_label(6, "周日"),
        "周末": f"{_next_weekday_label(5, '周六')}-{_next_weekday_label(6, '周日')}",
    }
    for token, label in relative_dates.items():
        if token in message and label not in parts:
            parts.append(label)
    for token in ["工作日", "一天", "两天", "三天", "半天"]:
        if token in message and token not in " ".join(parts):
            parts.append(token)
    english_tokens = {
        "today": "今天",
        "tomorrow": "明天",
        "weekend": "周末",
        "saturday": "周六",
        "sunday": "周日",
        "one day": "一天",
        "half day": "半天",
    }
    lower_message = message.lower()
    for token, label in english_tokens.items():
        if token in lower_message and label not in parts:
            parts.append(label)
    for token in ["上午", "中午", "下午", "傍晚", "晚上", "夜间"]:
        if token in message and token not in parts:
            parts.append(token)

    return " ".join(parts) if parts else None


def _extract_start_location(message: str) -> str | None:
    match = re.search(r"(?:当前位置|当前坐标|坐标|起点)[:：]?\s*(-?\d{2,3}\.\d+)\s*[,，]\s*(-?\d{1,2}\.\d+)", message)
    if match:
        return f"{match.group(1)},{match.group(2)}"
    raw = _extract_structured_field_any(message, ["起点", "出发地", "Start point", "Origin"])
    if raw:
        coord = re.search(r"(-?\d{2,3}\.\d+)\s*[,，]\s*(-?\d{1,2}\.\d+)", raw)
        if coord:
            return f"{coord.group(1)},{coord.group(2)}"
        return raw.strip()
    return None


def _extract_start_location_label(message: str) -> str | None:
    raw = _extract_structured_field_any(message, ["起点", "出发地", "Start point", "Origin"])
    if not raw:
        return None
    cleaned = re.sub(r"^-?\d{2,3}\.\d+\s*[,，]\s*-?\d{1,2}\.\d+\s*[,，]?\s*", "", raw).strip()
    if not cleaned:
        return None
    cleaned = re.split(r"[\n;；]", cleaned, 1)[0].strip(" ，,")
    return cleaned[:40] or None


def _extract_structured_field(message: str, label: str) -> str | None:
    match = re.search(rf"{label}\s*[:：]\s*([^\n]+)", message)
    return match.group(1).strip() if match else None


def _extract_structured_field_any(message: str, labels: list[str]) -> str | None:
    for label in labels:
        value = _extract_structured_field(message, label)
        if value:
            return value
    return None


def _extract_districts(message: str) -> list[str]:
    raw = _extract_structured_field_any(message, ["考虑区县", "区县", "Districts", "Areas"])
    if not raw:
        return []
    parts = re.split(r"[、,，/\s]+", raw)
    return [part.strip() for part in parts if part.strip()]


def _extract_daily_time_range(message: str) -> tuple[str | None, str | None, int | None]:
    raw = _extract_structured_field_any(message, ["每日时间", "时间", "时间范围", "Daily time", "Time", "Time window"])
    if not raw:
        return None, None, None
    match = re.search(r"(\d{1,2})[:：](\d{2})\s*(?:-|－|—|–|~|～|至|到)\s*(\d{1,2})[:：](\d{2})", raw)
    if not match:
        return None, None, None
    sh, sm, eh, em = map(int, match.groups())
    start = f"{sh:02d}:{sm:02d}"
    end = f"{eh:02d}:{em:02d}"
    start_min = sh * 60 + sm
    end_min = eh * 60 + em
    if end_min <= start_min:
        end_min += 24 * 60
    return start, end, max(120, end_min - start_min)


def _extract_structured_date_range(message: str) -> str | None:
    raw = _extract_structured_field_any(message, ["出行日期", "日期", "Travel dates", "Dates"])
    if not raw:
        return None
    return raw.replace("至", "-").replace("到", "-")


def _infer_daily_start_time(message: str, time_slot: str | None, trip_days: int) -> str:
    text = f"{message} {time_slot or ''}"
    explicit = re.search(r"(\d{1,2})[:：点](\d{1,2})?", text)
    if explicit:
        hour = int(explicit.group(1))
        minute = int(explicit.group(2) or 0)
        return f"{hour:02d}:{minute:02d}"
    if "上午" in text:
        return "09:30"
    if "中午" in text:
        return "11:30"
    if "下午" in text:
        return "13:30"
    if "晚上" in text or "夜间" in text:
        return "18:30"
    if trip_days > 1:
        return "10:00"
    if "周末" in text or "周六" in text or "周日" in text or "一天" in text:
        return "09:30"
    return "10:00"


def _extract_preferences(message: str) -> list[str]:
    preferences: list[str] = []
    lower_message = message.lower()
    for keywords, values in PREFERENCE_PATTERNS:
        if any(keyword in message or keyword.lower() in lower_message for keyword in keywords):
            preferences.extend(values)
    if (
        "不排队" in message
        or "少排队" in message
        or "别排队" in message
        or "控排队" in message
        or "排队可控" in message
        or "avoid queues" in lower_message
        or "less queue" in lower_message
        or "fewer queues" in lower_message
        or "no queues" in lower_message
        or "manageable queues" in lower_message
    ):
        preferences.append("少排队")
    return _merge_unique(preferences)


def _is_english_request(message: str) -> bool:
    ascii_letters = sum(1 for ch in message if ("a" <= ch.lower() <= "z"))
    chinese_chars = sum(1 for ch in message if "\u4e00" <= ch <= "\u9fff")
    return ascii_letters >= 8 and ascii_letters > chinese_chars


def _extract_modify(message: str) -> tuple[str | None, dict | None]:
    if any(word in message for word in ["少走路", "近一点", "别太远", "少走"]):
        return "less_walking", None
    if any(word in message for word in ["不排队", "少排队", "别排队"]):
        return "less_queue", None
    if any(word in message for word in ["省钱", "便宜", "降低预算"]):
        return "lower_budget", None
    replace_categories = {
        "餐厅": ["换餐厅", "换吃的", "换饭店"],
        "咖啡": ["换咖啡", "换个咖啡"],
        "景点": ["换景点", "换地方"],
    }
    for category, keywords in replace_categories.items():
        if any(keyword in message for keyword in keywords):
            return "replace_poi", {"category": category}
    return None, None


def _rule_extract_trip_fields(message: str, state: PlannerState | None = None) -> dict:
    state = state or {}
    data: dict = {}
    if _is_english_request(message):
        data["language"] = "en"
    language_raw = _extract_structured_field_any(message, ["语言", "Language"])
    if language_raw and language_raw.lower() in {"english", "en", "英文"}:
        data["language"] = "en"
    elif language_raw and language_raw.lower() in {"chinese", "zh", "简体中文", "中文"}:
        data["language"] = "zh"

    city = _extract_city(message)
    structured_city = _extract_structured_field_any(message, ["城市", "City"])
    if structured_city:
        city = _normalize_city_alias(structured_city)
    if city:
        data["location"] = _normalize_city_alias(city) or city
    districts = _extract_districts(message)
    if districts:
        data["districts"] = districts
        data["area"] = "、".join(districts)

    budget = _extract_budget(message)
    if budget is not None:
        data["budget"] = budget

    people_count = _extract_people_count(message)
    if people_count is not None:
        data["people_count"] = people_count

    trip_days = _extract_trip_days(message)
    if trip_days is not None:
        data["trip_days"] = trip_days

    structured_date = _extract_structured_date_range(message)
    time_slot = _extract_time_slot(structured_date or message)
    if time_slot:
        data["time_slot"] = time_slot

    daily_start, daily_end, daily_duration = _extract_daily_time_range(message)
    if daily_start:
        data["daily_start_time"] = daily_start
    if daily_end:
        data["daily_end_time"] = daily_end
    if daily_duration:
        data["daily_duration_minutes"] = daily_duration

    start_location = _extract_start_location(message)
    if start_location:
        data["start_location"] = start_location
        start_label = _extract_start_location_label(message)
        if start_label:
            data["start_location_label"] = start_label

    preferences = _extract_preferences(message)
    if preferences:
        data["preferences"] = preferences

    modify_action, modify_payload = _extract_modify(message)
    has_existing_itinerary = bool(state.get("itinerary"))
    if modify_action and has_existing_itinerary:
        data.pop("location", None)
        data.pop("time_slot", None)
        data.pop("trip_days", None)
        data.pop("start_location", None)
        data["intent"] = "modify"
        data["modify_action"] = modify_action
        data["modify_payload"] = modify_payload
        data["force_generate"] = True
    elif modify_action == "less_queue":
        data.setdefault("preferences", [])
        data["preferences"] = _merge_unique(data["preferences"] + ["少排队"])
        data["intent"] = "plan"
    elif any(key in data for key in ["location", "budget", "preferences", "people_count", "time_slot", "trip_days", "districts"]):
        data["intent"] = "plan"
    else:
        data["intent"] = "chat"

    enough_to_generate = bool(
        (data.get("location") or state.get("location"))
        and (data.get("time_slot") or state.get("time_slot"))
        and (data.get("budget") or state.get("budget") or data.get("preferences") or state.get("preferences"))
    )
    if enough_to_generate:
        data["force_generate"] = True

    if any(word in message for word in ["直接生成", "不用问", "先给方案", "就这样", "随便"]):
        data["force_generate"] = True
        data["intent"] = "plan"

    return data


def _merge_intent_data(llm_data: dict | None, rule_data: dict) -> dict:
    data = llm_data or {}
    result = {
        "intent": data.get("intent") or rule_data.get("intent", "plan"),
        "force_generate": bool(data.get("force_generate") or rule_data.get("force_generate", False)),
    }

    for key in ["modify_action", "modify_payload"]:
        val = data.get(key)
        if val is None:
            val = rule_data.get(key)
        if val is not None and val != "null":
            result[key] = val

    for field in ["location", "budget", "preferences", "people_count", "time_slot", "area", "districts"]:
        val = data.get(field)
        if val in (None, "null", ""):
            val = rule_data.get(field)
        if val not in (None, "null", ""):
            result[field] = val

    for field in ["trip_days", "start_location", "start_location_label", "language", "daily_start_time", "daily_end_time", "daily_duration_minutes"]:
        val = rule_data.get(field)
        if val not in (None, "null", ""):
            result[field] = val

    if result.get("modify_action"):
        result["intent"] = "modify"
        result["force_generate"] = True

    return result


def intent_node(state: PlannerState, llm) -> dict:
    _log("intent", f"进入意图识别, 消息数={len(state.get('messages', []))}")
    message = state["messages"][-1].content
    rule_data = _rule_extract_trip_fields(message, state)

    if rule_data.get("force_generate") or (
        rule_data.get("location")
        and rule_data.get("time_slot")
        and (rule_data.get("budget") or rule_data.get("preferences"))
    ):
        result = _merge_intent_data(None, rule_data)
        if result.get("intent") == "modify" and not state.get("itinerary"):
            result["intent"] = "plan"
            result.pop("modify_action", None)
            result.pop("modify_payload", None)
        _log(
            "intent",
            f"规则命中: intent={result.get('intent')}, location={result.get('location')}, "
            f"budget={result.get('budget')}, people={result.get('people_count')}, force={result.get('force_generate')}",
        )
        return result

    context = build_context(state)
    prompt = INTENT_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "未知",
        preferences=state.get("preferences") or "未知",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "未知",
        message=message,
    )

    llm_data = None
    try:
        response = llm.invoke(context + [HumanMessage(content=prompt)])
        llm_data = _parse_json(response.content)
    except Exception as exc:
        _log("intent", f"LLM不可用，使用规则解析: {type(exc).__name__}")

    result = _merge_intent_data(llm_data, rule_data)
    if result.get("intent") == "modify" and not state.get("itinerary"):
        # 首次规划里出现“不排队/少走路/省钱”是约束，不是对已有路线的修改。
        result["intent"] = "plan"
        result.pop("modify_action", None)
        result.pop("modify_payload", None)
    _log(
        "intent",
        f"结果: intent={result.get('intent')}, location={result.get('location')}, "
        f"budget={result.get('budget')}, people={result.get('people_count')}, force={result.get('force_generate')}",
    )
    return result


def check_node(state: PlannerState) -> dict:
    required = ["location", "time_slot"]
    has_required = all(state.get(f) for f in required)
    has_optional = bool(state.get("budget") or state.get("preferences") or state.get("people_count"))
    info_complete = has_required and has_optional

    _log(
        "check",
        f"完整性检查: location={state.get('location')}, time={state.get('time_slot')}, "
        f"budget={state.get('budget')}, prefs={state.get('preferences')} -> complete={info_complete}",
    )

    return {
        "info_complete": info_complete,
        "turn_number": state.get("turn_number", 0) + 1,
    }


def _fallback_ask_message(missing: list[str]) -> str:
    if not missing:
        return "我可以开始规划了。"
    short = "、".join(missing[:2])
    return f"还需要确认：{short}。补充后我会直接给出可执行路线。"


def ask_node(state: PlannerState, llm) -> dict:
    missing = []
    if not state.get("location"):
        missing.append("城市或区域")
    if not state.get("time_slot"):
        missing.append("出行时间")
    if not state.get("budget") and not state.get("preferences"):
        missing.append("预算或偏好")

    context = build_context(state)
    prompt = ASK_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "未知",
        preferences=state.get("preferences") or "未知",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "未知",
        missing="、".join(missing),
    )

    try:
        response = llm.invoke(context + [HumanMessage(content=prompt)])
        content = response.content
    except Exception as exc:
        _log("ask", f"LLM不可用，使用固定追问: {type(exc).__name__}")
        content = _fallback_ask_message(missing)

    return {
        "messages": [AIMessage(content=content)],
        "ask_count": state.get("ask_count", 0) + 1,
    }


def chat_node(state: PlannerState, llm) -> dict:
    context = build_context(state)
    try:
        response = llm.invoke(context + [HumanMessage(content=CHAT_PROMPT)])
        content = response.content
    except Exception as exc:
        _log("chat", f"LLM不可用，使用固定闲聊回复: {type(exc).__name__}")
        content = "我是 Roam 漫游。你可以直接说城市/区域、时间、人数、预算和偏好，我会给出多条可执行路线。"

    return {"messages": [AIMessage(content=content)]}


def _base_constraints_from_state(state: PlannerState) -> dict:
    location = (state.get("location") or "").replace("市", "").replace("区", "")
    return {
        "city": location or None,
        "area": state.get("location"),
        "districts": [],
        "time_slot": state.get("time_slot"),
        "trip_days": 1,
        "daily_start_time": "10:00",
        "start_location": None,
        "start_location_label": None,
        "budget": state.get("budget"),
        "people_count": state.get("people_count") or 1,
        "preferences": state.get("preferences", []),
        "avoid_tags": [],
        "transport_mode": "walking",
        "queue_tolerance": 1 if "排队" in _last_human_message(state) else 2,
        "pace": "relaxed" if any(word in _last_human_message(state) for word in ["轻松", "少走路", "别太累"]) else "balanced",
        "must_visit": [],
        "language": "zh",
    }


def _merge_rule_into_constraints(constraints: dict, message: str, state: PlannerState) -> dict:
    rule_data = _rule_extract_trip_fields(message, state)
    result = {**constraints}
    if rule_data.get("location"):
        result["city"] = rule_data["location"]
        result["area"] = rule_data["location"]
    if rule_data.get("area"):
        result["area"] = rule_data["area"]
    if rule_data.get("districts"):
        result["districts"] = rule_data["districts"]
    if rule_data.get("budget") is not None:
        result["budget"] = rule_data["budget"]
    if rule_data.get("people_count") is not None:
        result["people_count"] = rule_data["people_count"]
    if rule_data.get("time_slot"):
        result["time_slot"] = rule_data["time_slot"]
    if rule_data.get("trip_days"):
        result["trip_days"] = rule_data["trip_days"]
    if rule_data.get("start_location"):
        result["start_location"] = rule_data["start_location"]
        if "," not in str(rule_data["start_location"]):
            result["start_location_label"] = rule_data["start_location"]
    if rule_data.get("start_location_label"):
        result["start_location_label"] = rule_data["start_location_label"]
    if rule_data.get("daily_start_time"):
        result["daily_start_time"] = rule_data["daily_start_time"]
    if rule_data.get("daily_end_time"):
        result["daily_end_time"] = rule_data["daily_end_time"]
    if rule_data.get("daily_duration_minutes"):
        result["daily_duration_minutes"] = rule_data["daily_duration_minutes"]
    if rule_data.get("language"):
        result["language"] = rule_data["language"]
    if not rule_data.get("daily_duration_minutes") and not result.get("duration_minutes"):
        result["duration_minutes"] = _estimate_duration_minutes(result.get("time_slot") or message)
    if rule_data.get("preferences"):
        result["preferences"] = _merge_unique(list(result.get("preferences") or []) + rule_data["preferences"])
    result["trip_days"] = _estimate_trip_days(result.get("time_slot") or message, result.get("duration_minutes"), result.get("trip_days"))
    if rule_data.get("daily_duration_minutes"):
        result["duration_minutes"] = int(rule_data["daily_duration_minutes"]) * max(1, int(result.get("trip_days") or 1))
    result.update(_budget_profile(result.get("budget"), result.get("people_count"), result.get("trip_days")))
    result["persona_strategy"] = _infer_persona_strategy(result.get("preferences") or [])
    if not rule_data.get("daily_start_time"):
        result["daily_start_time"] = _infer_daily_start_time(message, result.get("time_slot"), result["trip_days"])
    if (result["trip_days"] > 1 or len(result.get("districts") or []) > 1) and result.get("transport_mode") == "walking":
        result["transport_mode"] = "transit"
    if set(result.get("preferences") or []) & {"爬山", "户外"} and not re.search(r"\d{1,2}[:：点]", message):
        result["daily_start_time"] = "08:30"
    late_keywords = ["夜景", "酒吧", "演出", "音乐节", "晚上", "电竞", "游戏", "密室", "剧本杀", "夜市"]
    if not rule_data.get("daily_end_time"):
        result["daily_end_time"] = "22:00" if any(word in message for word in late_keywords) else "20:30"
    result["time_strategy"] = _build_time_strategy(result)
    if "排队" in message or "queue" in message.lower():
        result["queue_tolerance"] = 1
        result["avoid_tags"] = _merge_unique(list(result.get("avoid_tags") or []) + ["排队"])
    if any(word in message for word in ["小红书", "种草", "攻略", "避雷", "网红", "出片"]):
        result["ugc_source"] = "xhs"
    if any(word in message for word in ["少走路", "少赶路", "轻松", "别太累", "不要太累", "不要太赶"]):
        result["pace"] = "relaxed"
        result["distance_weight_boost"] = 2.2
    if any(word in message for word in ["吃顿好的", "吃一顿好的", "吃点好的", "吃好", "好好吃", "晚餐提档", "评分高", "高分餐厅", "better food", "good meal", "better dinner", "high-rated"]):
        result["food_priority"] = "quality"
        result["budget_target_ratio"] = max(float(result.get("budget_target_ratio") or 0.72), 0.86)
    if set(result.get("preferences") or []) & {"休闲"}:
        result["pace"] = "relaxed"
        result["distance_weight_boost"] = max(float(result.get("distance_weight_boost") or 1.0), 1.8)
    if set(result.get("preferences") or []) & {"爬山", "户外"}:
        result["pace"] = "active"
    if any(word in message for word in ["紧凑", "赶时间", "多去几个"]):
        result["pace"] = "intense"
    return result


def _budget_profile(budget: int | None, people_count: int | None, trip_days: int | None) -> dict:
    if not budget:
        return {"budget_level": "open", "budget_target_ratio": 0.72}
    people = max(1, int(people_count or 1))
    days = max(1, int(trip_days or 1))
    per_person_day = budget / people / days
    if per_person_day <= 120:
        return {"budget_level": "tight", "budget_target_ratio": 0.62, "budget_note": "预算偏紧，优先免费景点和高性价比餐饮。"}
    if per_person_day <= 260:
        return {"budget_level": "value", "budget_target_ratio": 0.76, "budget_note": "预算适中，保留核心体验并控制高价项目数量。"}
    if per_person_day <= 500:
        return {"budget_level": "balanced", "budget_target_ratio": 0.84, "budget_note": "预算较充足，可加入更好的餐饮、展览或夜间体验。"}
    if per_person_day <= 900:
        return {"budget_level": "comfort", "budget_target_ratio": 0.88, "budget_note": "预算充足，优先提高体验质量而不是单纯省钱。"}
    return {"budget_level": "premium", "budget_target_ratio": 0.92, "budget_note": "高预算，路线会主动加入高价值餐饮、购物或付费体验。"}


def _estimate_duration_minutes(time_text: str) -> int | None:
    text = time_text or ""
    range_days = _days_from_date_range(_extract_date_range_parts(text))
    if range_days:
        return range_days * 540
    explicit_days = _extract_trip_days(text)
    if explicit_days:
        return explicit_days * 540
    if _single_date_from_text(text):
        return 540
    if "三天" in text:
        return 3 * 540
    if "两天" in text or "2天" in text:
        return 2 * 540
    if any(token in text for token in ["今天", "明天", "后天", "周六", "周日", "周末"]):
        return 540
    if "一天" in text or "一日" in text or "整天" in text:
        return 540
    if "半天" in text or "上午" in text or "下午" in text or "晚上" in text:
        return 240
    return None


def _estimate_trip_days(time_text: str, duration_minutes: int | None, existing: int | None = None) -> int:
    text = time_text or ""
    range_days = _days_from_date_range(_extract_date_range_parts(text))
    if range_days:
        return range_days
    explicit_days = _extract_trip_days(text)
    if explicit_days:
        return explicit_days
    if existing and int(existing) > 1:
        return max(1, min(int(existing), 14))
    if duration_minutes:
        return max(1, min(round(duration_minutes / 540), 14))
    if existing:
        return max(1, min(int(existing), 14))
    return 1


def _build_time_strategy(constraints: dict) -> dict:
    trip_days = constraints.get("trip_days") or 1
    start_time = constraints.get("daily_start_time", "10:00")
    end_time = constraints.get("daily_end_time", "20:30")
    time_slot = constraints.get("time_slot") or "未指定"
    persona = constraints.get("persona_strategy") or _infer_persona_strategy(constraints.get("preferences") or [])
    start_hour = _hour_from_time(start_time)
    if constraints.get("language") == "en":
        if trip_days > 1:
            note = f"{trip_days}-day itinerary split by {start_time}-{end_time}; the first day starts slightly lighter to avoid overloading arrival time."
        elif start_hour is not None and start_hour >= 16:
            note = f"Plan starts around {start_time}; focus on dinner, evening entertainment and night-view continuity."
        elif any(word in str(time_slot) for word in ["周末", "周六", "周日"]):
            note = f"Weekend plan starts around {start_time}; popular restaurants are shifted toward brunch or afternoon tea to reduce queues."
        else:
            note = f"Plan starts around {start_time} and keeps room for lunch, coffee and evening flexibility."
    elif trip_days > 1:
        note = f"{trip_days}天行程按每天{start_time}-{end_time}拆分，第一天略晚启动，避免到达日过满。"
    elif start_hour is not None and start_hour >= 16:
        note = f"按{start_time}出发，重点安排晚餐、娱乐和夜景连续动线。"
    elif any(word in str(time_slot) for word in ["周末", "周六", "周日"]):
        note = f"周末按{start_time}出发，热门餐饮尽量错峰到早午餐或下午茶。"
    else:
        note = f"按{start_time}出发，保留午餐、下午茶和晚间弹性。"
    if persona.get("time_note"):
        note = f"{note} {persona['time_note']}"
    return {
        "daily_start_time": start_time,
        "daily_end_time": end_time,
        "trip_days": trip_days,
        "note": note,
        "persona": persona,
    }


def _hour_from_time(value: str | None) -> int | None:
    match = re.match(r"^(\d{1,2}):", str(value or ""))
    if not match:
        return None
    return int(match.group(1))


def _infer_persona_strategy(preferences: list[str]) -> dict:
    prefs = set(preferences or [])
    if prefs & {"爬山", "户外"}:
        return {
            "name": "户外体力型",
            "time_note": "爬山/徒步优先放在上午，下午安排补给、咖啡或轻松景点恢复体力。",
            "category_order": ["公园", "景点", "餐厅", "咖啡", "展览", "购物", "夜景"],
        }
    if "游戏" in prefs:
        return {
            "name": "游戏娱乐型",
            "time_note": "游戏、电竞、密室和桌游更适合下午或晚间，上午不强行塞满景点。",
            "category_order": ["咖啡", "展览", "餐厅", "娱乐", "购物", "夜景"],
        }
    if "购物" in prefs or "热闹" in prefs:
        return {
            "name": "商圈逛吃型",
            "time_note": "逛街放在下午到傍晚，和餐饮、夜景形成同片区连续动线。",
            "category_order": ["咖啡", "购物", "餐厅", "甜品", "夜景"],
        }
    if "亲子" in prefs:
        return {
            "name": "亲子轻松型",
            "time_note": "亲子路线控制转场和排队，上午安排博物馆/公园，下午留休息点。",
            "category_order": ["公园", "展览", "餐厅", "甜品", "景点"],
        }
    if "休闲" in prefs:
        return {
            "name": "休闲放松型",
            "time_note": "放松型路线减少硬核景点堆叠，优先安排好餐、咖啡/甜品、轻体验和不赶路的休息段。",
            "category_order": ["餐厅", "咖啡", "甜品", "公园", "娱乐", "夜景", "购物"],
        }
    return {
        "name": "综合探索型",
        "time_note": "按景点、正餐、休息、体验和夜间活动组合，避免模板化堆点。",
        "category_order": ["景点", "展览", "餐厅", "咖啡", "购物", "夜景"],
    }


def _district_radius(area_info: dict | None) -> int:
    radius = int((area_info or {}).get("radius") or 9000)
    level = str((area_info or {}).get("level") or "")
    if "区县" in level or "district" in level:
        return min(max(radius, 3500), 6000)
    return radius


def _parse_lnglat(value: str | None) -> tuple[float, float] | None:
    if not value or "," not in str(value):
        return None
    try:
        lng, lat = str(value).split(",", 1)
        return float(lng), float(lat)
    except (TypeError, ValueError):
        return None


def _is_lnglat(value: str | None) -> bool:
    return _parse_lnglat(value) is not None


def _resolve_start_location_constraint(constraints: dict) -> dict:
    raw = str(constraints.get("start_location") or "").strip()
    if not raw:
        return constraints
    if _is_lnglat(raw):
        constraints.setdefault("start_location_label", "当前位置" if "当前位置" in raw else "起点")
        return constraints

    city = constraints.get("city") or ""
    try:
        from tools.amap import geocode_location

        payload = json.loads(geocode_location.invoke({"address": raw, "city": city}))
    except Exception:
        return constraints

    if isinstance(payload, list) and payload:
        item = payload[0]
        if item.get("location"):
            constraints["start_location_raw"] = raw
            constraints["start_location"] = item["location"]
            constraints["start_location_label"] = raw
            constraints["start_location_address"] = item.get("formatted_address") or raw
    return constraints


def _city_district_names(city: str) -> list[tuple[str, str]]:
    try:
        from tools.amap import district_search

        payload = json.loads(district_search.invoke({"keyword": city, "subdistrict": 1}))
    except Exception:
        return []
    districts: list[tuple[str, str]] = []
    for item in payload if isinstance(payload, list) else []:
        children = item.get("districts") or []
        for child in children:
            name = str(child.get("name") or "")
            if not name:
                continue
            short = name.replace("区", "").replace("县", "")
            districts.append((name, short))
    return list(dict.fromkeys(districts))


def _filter_pois_for_district(pois: list[dict], district: str, area_info: dict | None, known_districts: list[tuple[str, str]] | None = None) -> list[dict]:
    expected_adcode = str((area_info or {}).get("adcode") or "")
    district_name = (district or "").strip()
    district_short = district_name.replace("区", "").replace("县", "")
    center = str((area_info or {}).get("center") or "")
    radius = _district_radius(area_info)
    filtered: list[dict] = []

    for poi in pois:
        poi_adcode = str(poi.get("adcode") or "")
        if expected_adcode and poi_adcode:
            if poi_adcode == expected_adcode:
                filtered.append(poi)
            continue

        text = " ".join(str(poi.get(field) or "") for field in ["address", "name", "tags"])
        mentioned_districts = set(re.findall(r"[\u4e00-\u9fa5]{1,8}[区县]", text))
        if district_name and district_name in text:
            filtered.append(poi)
            continue
        if district_short and district_short in text and not mentioned_districts:
            filtered.append(poi)
            continue
        if known_districts:
            matched_other_district = False
            for full_name, short_name in known_districts:
                if full_name == district_name:
                    continue
                if full_name and full_name in text:
                    matched_other_district = True
                    break
                if short_name and len(short_name) >= 2 and short_name in text:
                    matched_other_district = True
                    break
            if matched_other_district:
                continue
        if mentioned_districts and district_name not in mentioned_districts:
            continue

        if center and "," in center and poi.get("lng") is not None and poi.get("lat") is not None:
            try:
                from services.route_optimizer import haversine_distance

                center_lng, center_lat = [float(part) for part in center.split(",", 1)]
                if haversine_distance(float(poi["lng"]), float(poi["lat"]), center_lng, center_lat) <= radius:
                    filtered.append(poi)
            except (TypeError, ValueError):
                continue

    return filtered


def _filter_low_value_for_budget(pois: list[dict], constraints: dict, minimum_keep: int) -> list[dict]:
    budget_level = constraints.get("budget_level")
    wants_better_food = "美食" in set(constraints.get("preferences") or [])
    if budget_level not in {"balanced", "comfort", "premium"} and not wants_better_food:
        return pois
    low_value_keywords = ("肯德基", "KFC", "麦当劳", "汉堡王", "蜜雪冰城", "便利店", "超市", "萨莉亚", "Saizeriya", "必胜客")
    filtered = []
    for poi in pois:
        text = " ".join(str(poi.get(field) or "") for field in ["name", "address", "tags"])
        if poi.get("category") in {"餐厅", "咖啡", "甜品"} and any(keyword in text for keyword in low_value_keywords):
            continue
        filtered.append(poi)
    return filtered if len(filtered) >= minimum_keep else pois


def _poi_tag_list(poi: dict) -> list[str]:
    tags = poi.get("tags", [])
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            return parsed if isinstance(parsed, list) else [tags]
        except json.JSONDecodeError:
            return [tags]
    return tags if isinstance(tags, list) else []


def _poi_unit_price(poi: dict) -> int:
    tags = _poi_tag_list(poi)
    return int(poi.get("avg_cost") or 0) or _default_unit_price(
        str(poi.get("category") or ""),
        tags,
        str(poi.get("name") or ""),
        str(poi.get("address") or ""),
    )


def _build_upgrade_suggestions(pois: list[dict], constraints: dict, limit: int = 4) -> list[dict]:
    """从本地候选 POI 中挑出需要提高部分预算才值得加入的升级项。"""
    if not pois:
        return []

    language = constraints.get("language", "zh")
    preferences = set(constraints.get("preferences") or [])
    people_count = max(1, int(constraints.get("people_count") or 1))
    budget = int(constraints.get("budget") or 0)
    per_person_budget = budget / people_count if budget else 300
    min_total_cost = max(90 * people_count, int(max(per_person_budget * 0.34, 90) * people_count))
    premium_categories = {"餐厅", "娱乐", "购物", "夜景", "展览", "景点"}
    persona_keywords = {
        "美食": ("酒家", "食府", "海鲜", "私房菜", "粤菜", "火锅", "烧肉", "茶楼", "餐厅"),
        "休闲": ("SPA", "按摩", "汤泉", "温泉", "下午茶", "咖啡", "茶"),
        "游戏": ("电竞", "电玩", "密室", "剧本杀", "桌游", "游戏"),
        "娱乐": ("演出", "剧场", "Livehouse", "livehouse", "音乐", "娱乐"),
        "购物": ("商场", "购物", "太古汇", "万象城", "K11", "天河城"),
        "夜景": ("夜景", "塔", "观景", "酒吧", "游船"),
        "看展": ("展", "博物馆", "美术馆", "艺术"),
        "爬山": ("山", "森林", "步道", "公园", "景区"),
    }
    start_hour = _hour_from_time(constraints.get("daily_start_time")) or 10
    end_hour = _hour_from_time(constraints.get("daily_end_time")) or 22
    institutional_keywords = ("文化馆", "图书馆", "少年宫", "党群", "服务中心", "政务", "学校", "医院", "停车场")
    night_fit_keywords = (
        "夜景", "夜游", "观景", "塔", "游船", "酒吧", "Livehouse", "livehouse", "音乐", "演出",
        "剧场", "影院", "电影", "电竞", "电玩", "密室", "桌游", "KTV", "商场", "购物", "餐厅",
        "酒家", "食府", "火锅", "烧肉", "咖啡", "甜品", "茶楼", "按摩", "SPA", "汤泉",
    )
    daytime_only_keywords = ("博物馆", "美术馆", "展览馆", "文化馆", "图书馆", "公园", "森林公园", "山")

    scored = []
    seen = set()
    for poi in pois:
        name = str(poi.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        category = str(poi.get("category") or "")
        tags = _poi_tag_list(poi)
        text = " ".join([name, str(poi.get("address") or ""), category, *map(str, tags)])
        unit_price = _poi_unit_price(poi)
        total_cost = unit_price * people_count
        if any(keyword in text for keyword in institutional_keywords) and not any(keyword in text for keyword in ("演出", "音乐", "剧场", "livehouse", "Livehouse")):
            continue
        if start_hour >= 16 and any(keyword in text for keyword in daytime_only_keywords) and not any(keyword in text for keyword in night_fit_keywords):
            continue
        if end_hour >= 20 and category in {"景点", "展览"} and any(keyword in text for keyword in daytime_only_keywords) and not any(keyword in text for keyword in night_fit_keywords):
            continue
        if category not in premium_categories and total_cost < min_total_cost:
            continue
        if total_cost < min_total_cost and not any(keyword in text for words in persona_keywords.values() for keyword in words):
            continue

        pref_score = 0
        matched_pref = []
        for pref, keywords in persona_keywords.items():
            if pref in preferences and any(keyword in text for keyword in keywords):
                pref_score += 2
                matched_pref.append(pref)
            elif any(keyword in text for keyword in keywords):
                pref_score += 0.6
        cost_score = min(total_cost / max(min_total_cost, 1), 2.2)
        rating_score = float(poi.get("rating") or 4.0) / 5
        scored.append((pref_score + cost_score + rating_score + float(poi.get("_score") or 0), poi, total_cost, matched_pref))

    scored.sort(key=lambda item: item[0], reverse=True)
    suggestions = []
    for _, poi, total_cost, matched_pref in scored[:limit]:
        name = str(poi.get("name") or "")
        category = str(poi.get("category") or "")
        tags = _poi_tag_list(poi)
        if language == "en":
            reason = "matches " + ", ".join(matched_pref) if matched_pref else f"a higher-value {category or 'experience'} option"
            summary = f"Stretch the budget for {name}: estimated extra spend about ¥{total_cost}, {reason}."
        else:
            reason = "、".join(matched_pref) if matched_pref else (category or "体验")
            summary = f"若愿意上探部分预算，可考虑加入「{name}」：预计约 ¥{total_cost}，更贴合{reason}。"
        suggestions.append({
            "title": name,
            "summary": summary,
            "summary_en": summary if language == "en" else f"Optional upgrade: {name}, estimated ¥{total_cost}.",
            "estimated_cost": total_cost,
            "category": category,
            "tags": tags[:4],
            "reason": reason,
            "source": "local_poi_upgrade",
        })
    return suggestions


def collect_data_node(state: PlannerState, llm) -> dict:
    """解析约束、查询 POI、补全评价，支持修改逻辑。"""
    _log("collect_data", "进入数据收集节点")

    from services.intent_parser import parse_constraints, resolve_area
    from services.poi_service import search_or_fetch_pois
    from services.review_service import enrich_reviews
    from services.guide_service import build_city_guide

    existing_constraints = state.get("constraints")
    current_constraints = existing_constraints or _base_constraints_from_state(state)

    last_message = _last_human_message(state)
    constraints = _merge_rule_into_constraints(current_constraints, last_message, state)
    has_core_constraints = bool(
        constraints.get("city")
        and constraints.get("time_slot")
        and (constraints.get("budget") or constraints.get("preferences"))
    )
    if not has_core_constraints:
        try:
            constraints = parse_constraints(last_message, constraints, llm)
        except Exception as exc:
            _log("collect_data", f"约束LLM解析失败，使用规则解析: {type(exc).__name__}")
    if not constraints.get("city") and state.get("location"):
        constraints["city"] = state["location"]
    if not constraints.get("area") and state.get("location"):
        constraints["area"] = state["location"]
    constraints["people_count"] = max(1, int(constraints.get("people_count") or 1))
    constraints = _resolve_start_location_constraint(constraints)

    modify_action = state.get("modify_action")
    modify_payload = state.get("modify_payload") or {}
    if modify_action:
        if modify_action == "replace_poi":
            constraints["must_replace_type"] = modify_payload.get("category", "餐厅")
        elif modify_action == "less_walking":
            constraints["distance_weight_boost"] = 3.0
            constraints["pace"] = "relaxed"
        elif modify_action == "less_queue":
            constraints["queue_tolerance"] = 1
            constraints["avoid_tags"] = _merge_unique(list(constraints.get("avoid_tags") or []) + ["排队"])
        elif modify_action == "lower_budget":
            constraints["budget"] = int((constraints.get("budget") or 300) * 0.75)
        _log("collect_data", f"修改动作: {modify_action}")

    _log("collect_data", f"约束: {json.dumps(constraints, ensure_ascii=False)}")

    city = constraints.get("city") or "杭州"
    preferences = constraints.get("preferences", [])
    search_preferences = list(preferences)
    if constraints.get("budget_level") in {"comfort", "premium"} and set(preferences) & {"美食", "购物", "夜景", "热闹", "娱乐", "游戏", "探店"}:
        search_preferences = _merge_unique(search_preferences + ["娱乐", "探店"])
    if set(preferences) & {"美食", "休闲"}:
        search_preferences = _merge_unique(search_preferences + ["探店", "咖啡", "甜品", "娱乐"])
    if set(preferences) & {"游戏", "娱乐"}:
        search_preferences = _merge_unique(search_preferences + ["游戏", "娱乐", "夜景", "购物"])
    budget = constraints.get("budget")
    people_count = constraints.get("people_count") or 1
    max_cost = (budget / people_count) * 0.85 if budget else None

    poi_limit = min(56, max(26, int(constraints.get("trip_days") or 1) * 12))
    selected_districts = list(dict.fromkeys(constraints.get("districts") or []))
    area_info = resolve_area(constraints)
    pois = []
    if selected_districts:
        constraints["area"] = "、".join(selected_districts)
        district_count = max(1, len(selected_districts))
        per_area_limit = max(8, min(14, math_ceil(poi_limit / district_count) + 2))
        keyword_limit = 6 if district_count >= 2 else 10
        area_infos = []
        known_districts = _city_district_names(city)
        for district in selected_districts:
            district_constraints = {**constraints, "area": district, "start_location": None}
            district_info = resolve_area(district_constraints)
            area_infos.append(district_info)
            district_pois = search_or_fetch_pois(
                city,
                search_preferences,
                max_cost,
                limit=per_area_limit,
                area=district,
                adcode=district_info.get("adcode"),
                center=district_info.get("center"),
                radius_m=_district_radius(district_info),
                keyword_limit=keyword_limit,
            )
            pois.extend(_filter_pois_for_district(district_pois, district, district_info, known_districts))
        area_info = area_infos[0] if area_infos else area_info
        seen = set()
        deduped = []
        for poi in pois:
            key = poi.get("id") or poi.get("name")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(poi)
        pois = deduped[: max(poi_limit, 24)]
    else:
        pois = search_or_fetch_pois(
            city,
            search_preferences,
            max_cost,
            limit=poi_limit,
            area=constraints.get("area"),
            adcode=area_info.get("adcode"),
            center=area_info.get("center"),
            radius_m=area_info.get("radius"),
        )

    _log("collect_data", f"区域: {area_info}")
    if area_info.get("adcode"):
        constraints["adcode"] = area_info["adcode"]
    if area_info.get("resolved_name") and not constraints.get("resolved_name"):
        constraints["resolved_name"] = area_info["resolved_name"]

    pois = _filter_low_value_for_budget(pois, constraints, minimum_keep=max(8, min(poi_limit, 16)))

    if modify_action == "replace_poi" and state.get("itinerary"):
        replace_type = constraints.get("must_replace_type", "餐厅")
        current_ids = {
            b["id"]
            for b in state["itinerary"].get("blocks", [])
            if b.get("category") == replace_type
        }
        pois = [p for p in pois if p["id"] not in current_ids]
        _log("collect_data", f"排除 {len(current_ids)} 个同类 POI")

    _log("collect_data", f"找到 {len(pois)} 个 POI")

    remote_source = "xhs" if constraints.get("ugc_source") == "xhs" else "public_search"
    fetch_remote = constraints.get("ugc_source") == "xhs"
    pois = enrich_reviews(pois, fetch_remote=fetch_remote, remote_limit=4, remote_source=remote_source)
    _log("collect_data", "评价补全完成")
    upgrade_suggestions = _build_upgrade_suggestions(pois, constraints)
    if upgrade_suggestions:
        _log("collect_data", f"形成 {len(upgrade_suggestions)} 条升级建议")

    guide_trigger_prefs = {"美食", "咖啡", "探店", "热闹", "娱乐", "游戏", "夜景", "购物", "看展"}
    guide_keywords = ["小红书", "攻略", "避雷", "网红", "xhs", "xiaohongshu", "吃好", "好吃", "宝藏", "探店"]
    explicit_guide_need = any(word in last_message.lower() for word in guide_keywords)
    premium_guide_need = constraints.get("budget_level") in {"comfort", "premium"} and bool(set(preferences) & guide_trigger_prefs)
    should_build_guide = bool(
        not modify_action
        and (
            constraints.get("ugc_source") == "xhs"
            or explicit_guide_need
            or premium_guide_need
        )
    )
    guide_signals = build_city_guide(city, preferences) if should_build_guide else {}
    if guide_signals:
        constraints["guide_strategy"] = guide_signals.get("strategy", [])
        constraints["guide_positive_keywords"] = guide_signals.get("positive_keywords", [])
        constraints["guide_avoid_keywords"] = guide_signals.get("avoid_keywords", [])
        constraints["guide_hot_places"] = guide_signals.get("hot_places", [])
        _log("collect_data", f"形成攻略信号 {len(guide_signals.get('snippets', []))} 条")

    return {
        "constraints": constraints,
        "candidate_pois": pois,
        "area_info": area_info,
        "event_suggestions": [],
        "upgrade_suggestions": upgrade_suggestions,
        "guide_signals": guide_signals,
        "modify_action": None,
        "modify_payload": None,
    }


def rank_poi_node(state: PlannerState) -> dict:
    _log("rank_poi", "进入打分节点")

    from services.route_optimizer import score_poi

    pois = state.get("candidate_pois", [])
    constraints = state.get("constraints", {})
    area_info = state.get("area_info") or {}
    area_center = constraints.get("start_location") if _parse_lnglat(str(constraints.get("start_location") or "")) else area_info.get("center")

    for poi in pois:
        poi["_score"] = score_poi(poi, constraints, area_center=area_center)

    pois.sort(key=lambda x: x.get("_score", 0), reverse=True)
    _log("rank_poi", f"打分完成，Top3: {[p['name'] for p in pois[:3]]}")

    return {"candidate_pois": pois}


def _display_plan_name(name: str, constraints: dict) -> str:
    if constraints.get("language") != "en":
        return name
    mapping = {
        "综合推荐": "Best Overall",
        "吃好玩好": "Food & Fun",
        "省钱轻量": "Value Pick",
        "少走路": "Less Walking",
        "多日综合": "Multi-day Balanced",
        "预算充分": "Richer Budget Use",
        "少折返": "Compact Route",
        "轻松留白": "Relaxed Pace",
        "兴趣强化": "Interest First",
        "休闲放松": "Relaxed Comfort",
    }
    if name.startswith("备选方案"):
        return name.replace("备选方案", "Alternative ")
    return mapping.get(name, name)


def _display_highlights(highlights: list[str], constraints: dict) -> list[str]:
    if constraints.get("language") != "en":
        return highlights
    mapping = {
        "偏好匹配": "preference fit",
        "预算利用适中": "balanced budget use",
        "类型丰富": "varied stop types",
        "地点更集中": "more compact area",
        "步行距离更短": "shorter walking",
        "餐饮和消费体验更完整": "stronger dining and spending experience",
        "适合逛吃": "good for eating and browsing",
        "低消费": "lower cost",
        "保留核心体验": "keeps core experiences",
        "预算内优先": "keeps within budget first",
        "按天拆分": "split by day",
        "类型均衡": "balanced categories",
        "转场顺序优化": "optimized transfer order",
        "提高预算利用": "better budget use",
        "更多餐饮与体验消费": "more dining and experience spend",
        "适合不想太省": "less conservative",
        "减少跨城折返": "less backtracking",
        "每天集中片区": "clustered by area",
        "每天不过载": "not overloaded",
        "留出临时活动和休息时间": "keeps buffer time",
    }
    return [mapping.get(item, item) for item in highlights]


def _display_preferences(preferences: list[str], constraints: dict) -> str:
    if constraints.get("language") != "en":
        return "、".join(preferences or ["综合体验"])
    mapping = {
        "综合体验": "balanced experience",
        "美食": "food",
        "吃好": "better dining",
        "少排队": "fewer queues",
        "休闲": "relaxed pace",
        "放松": "relaxing stops",
        "自然": "nature",
        "夜景": "night views",
        "购物": "shopping",
        "探店": "hidden gems",
        "咖啡": "coffee",
        "甜品": "dessert",
        "娱乐": "entertainment",
        "游戏": "gaming",
        "看展": "exhibitions",
        "爬山": "hiking",
        "亲子": "family friendly",
    }
    return ", ".join(mapping.get(item, item) for item in (preferences or ["综合体验"]))


def build_itinerary_from_plan(
    plan: dict,
    matrix: dict,
    constraints: dict,
    people_count: int | None = None,
    transport_mode: str | None = None,
    event_suggestions: list[dict] | None = None,
    upgrade_suggestions: list[dict] | None = None,
    guide_signals: dict | None = None,
    all_pois: list[dict] | None = None,
    include_route_details: bool = False,
    include_start_detail: bool = False,
) -> dict:
    people_count = max(1, int(people_count or constraints.get("people_count") or 1))
    transport_mode = transport_mode or constraints.get("transport_mode", "walking")
    event_suggestions = event_suggestions or []
    upgrade_suggestions = upgrade_suggestions or []
    guide_signals = guide_signals or {}
    all_pois = all_pois or plan.get("route", [])

    blocks = _build_blocks(plan["route"], people_count)
    connections = _build_connections(plan["route"], matrix, transport_mode, constraints, include_details=include_route_details)
    day_plan = _split_into_days(blocks, connections, constraints, guide_signals)
    start_transfer = _build_start_transfer(
        constraints,
        day_plan["blocks"][0] if day_plan["blocks"] else None,
        include_details=include_start_detail,
    )
    if start_transfer:
        day_plan = _apply_start_transfer_to_day_plan(day_plan, int(start_transfer.get("duration_minutes") or 0), constraints)
        first_after_trim = day_plan["blocks"][0] if day_plan["blocks"] else None
        if first_after_trim and first_after_trim.get("id") != start_transfer.get("to"):
            start_transfer = _build_start_transfer(constraints, first_after_trim, include_details=include_start_detail)
        if start_transfer:
            day_plan = _inject_start_block(day_plan, start_transfer, constraints)

    actual_duration = sum(day.get("total_duration", 0) for day in day_plan["days"])
    actual_price = sum(block.get("price", 0) for block in day_plan["blocks"])
    return {
        "blocks": day_plan["blocks"],
        "connections": day_plan["connections"],
        "days": day_plan["days"],
        "total_duration": actual_duration or plan["score"].get("total_duration_s", 0) // 60,
        "total_price": actual_price or plan["score"].get("total_cost", 0),
        "score": plan["score"].get("route_score", 0),
        "plan_name": _display_plan_name(plan["name"], constraints),
        "style": plan.get("style", plan["name"]),
        "highlights": _display_highlights(plan.get("highlights", []), constraints),
        "total_distance": plan["score"].get("total_distance_m", 0) + int((start_transfer or {}).get("distance_m") or 0),
        "time_plan": constraints.get("time_strategy", {}),
        "event_suggestions": event_suggestions,
        "upgrade_suggestions": upgrade_suggestions,
        "guide_signals": guide_signals,
        "map_pois": _build_map_pois(all_pois, plan["route"], people_count),
        "start_transfer": start_transfer,
    }


def _budget_limit_value(constraints: dict | None) -> int | None:
    try:
        budget = int((constraints or {}).get("budget") or 0)
    except (TypeError, ValueError):
        budget = 0
    return budget if budget > 0 else None


def _itinerary_price(itinerary: dict | None) -> int:
    if not isinstance(itinerary, dict):
        return 0
    try:
        total = int(itinerary.get("total_price") or 0)
    except (TypeError, ValueError):
        total = 0
    if total > 0:
        return total
    blocks = itinerary.get("blocks") or []
    return sum(int(block.get("price") or 0) for block in blocks if isinstance(block, dict))


def _itinerary_within_budget(itinerary: dict | None, constraints: dict | None) -> bool:
    budget = _budget_limit_value(constraints)
    return budget is None or _itinerary_price(itinerary) <= budget


def optimize_route_node(state: PlannerState) -> dict:
    _log("optimize", "进入路线优化节点")

    from services.route_optimizer import optimize_route

    pois = state.get("candidate_pois", [])
    constraints = state.get("constraints", {})
    area_info = state.get("area_info") or {}
    area_center = area_info.get("center")
    transport_mode = constraints.get("transport_mode", "walking")

    dist_boost = constraints.get("distance_weight_boost", 1.0)
    duration_minutes = constraints.get("duration_minutes")
    trip_days = max(1, int(constraints.get("trip_days") or 1))
    if trip_days == 1 and duration_minutes and duration_minutes >= 480:
        max_stops = 8 if dist_boost <= 1.5 else 7
    elif trip_days == 1 and duration_minutes and duration_minutes >= 300:
        max_stops = 6 if dist_boost <= 1.5 else 6
    elif duration_minutes and duration_minutes >= 900:
        max_stops = 7
    elif duration_minutes and duration_minutes >= 720:
        max_stops = 6
    elif duration_minutes and duration_minutes >= 360:
        max_stops = 5
    else:
        max_stops = 4 if dist_boost > 1.5 else 5
    if constraints.get("pace") == "intense":
        max_stops = max(max_stops, 10 if trip_days == 1 else 7)
    if constraints.get("pace") == "active" and trip_days == 1:
        max_stops = min(max_stops, 6)

    opt_result = optimize_route(pois, constraints, max_stops=max_stops, area_center=area_center)
    plans = opt_result["plans"]
    matrix = opt_result["matrix"]
    _log("optimize", f"生成 {len(plans)} 个方案")

    if not plans:
        return {"itinerary": None, "alternative_plans": []}

    people_count = max(1, int(constraints.get("people_count") or 1))
    event_suggestions = state.get("event_suggestions", [])
    upgrade_suggestions = state.get("upgrade_suggestions", [])
    guide_signals = state.get("guide_signals", {})

    built_itineraries = [
        build_itinerary_from_plan(
            plan,
            matrix,
            constraints,
            people_count=people_count,
            transport_mode=transport_mode,
            event_suggestions=event_suggestions,
            upgrade_suggestions=upgrade_suggestions,
            guide_signals=guide_signals,
            all_pois=pois,
            include_route_details=False,
            include_start_detail=True,
        )
        for plan in plans
    ]

    if _budget_limit_value(constraints):
        budget_safe_itineraries = [
            itinerary for itinerary in built_itineraries
            if _itinerary_within_budget(itinerary, constraints)
        ]
        if not budget_safe_itineraries:
            _log("optimize", "没有找到预算内方案")
            return {"itinerary": None, "alternative_plans": []}
        built_itineraries = budget_safe_itineraries

    itinerary = built_itineraries[0]
    alternatives = built_itineraries[1:]
    itinerary["alternatives"] = alternatives

    return {
        "itinerary": itinerary,
        "alternative_plans": alternatives,
    }


def _build_start_transfer(constraints: dict, first_block: dict | None, include_details: bool = True) -> dict | None:
    start = _parse_lnglat(str(constraints.get("start_location") or ""))
    if not start or not first_block or first_block.get("lng") is None or first_block.get("lat") is None:
        return None
    try:
        from services.route_optimizer import haversine_distance

        distance_m = haversine_distance(start[0], start[1], float(first_block["lng"]), float(first_block["lat"]))
    except (TypeError, ValueError):
        return None

    if distance_m <= 1200:
        mode_zh, mode_en = "步行", "walking"
        minutes = max(5, round(distance_m / 75))
    elif distance_m <= 6000:
        mode_zh, mode_en = "公共交通", "public transit"
        minutes = max(14, round(distance_m / 280) + 8)
    elif distance_m > 120_000:
        mode_zh, mode_en = "跨城接驳", "intercity transfer"
        minutes = max(90, round(distance_m / 700) + 25)
    else:
        mode_zh, mode_en = "公共交通", "public transit"
        minutes = max(25, round(distance_m / 420) + 12)

    english = constraints.get("language") == "en"
    start_label = constraints.get("start_location_label") or ("Start point" if english else "起点")
    transfer = {
        "from": "start",
        "from_name": start_label,
        "to": first_block.get("id"),
        "to_name": first_block.get("name"),
        "from_lng": start[0],
        "from_lat": start[1],
        "to_lng": first_block.get("lng"),
        "to_lat": first_block.get("lat"),
        "distance": _format_distance(distance_m),
        "distance_m": round(distance_m),
        "time": f"{minutes}min" if english else f"{minutes}分钟",
        "duration_minutes": minutes,
        "mode": mode_en if english else mode_zh,
    }
    if not include_details:
        return transfer

    try:
        from tools.amap import fetch_direction_polyline, fetch_transit_plan

        origin = f"{start[0]},{start[1]}"
        destination = f"{first_block.get('lng')},{first_block.get('lat')}"
        transit_detail = None
        if mode_zh == "公共交通":
            transit_detail = fetch_transit_plan(
                origin,
                destination,
                str(constraints.get("adcode") or constraints.get("city") or ""),
                str(constraints.get("adcode") or constraints.get("city") or ""),
            )
            if transit_detail:
                transfer["transit_detail"] = transit_detail
                if transit_detail.get("duration"):
                    transfer["time"] = transit_detail["duration"] if not english else transit_detail["duration"].replace("分钟", "min")
                if transit_detail.get("route_path"):
                    transfer["route_path"] = transit_detail["route_path"]
                    transfer["route_path_source"] = "amap_transit"
        path_mode = "walking" if distance_m <= 1200 else "driving"
        route_path = transfer.get("route_path") or fetch_direction_polyline(origin, destination, path_mode)
        if route_path:
            transfer["route_path"] = route_path
            if not transfer.get("route_path_source") and path_mode == "driving" and distance_m > 1200:
                transfer["route_path_source"] = "driving_fallback"
    except Exception:
        pass
    return transfer


def _inject_start_block(day_plan: dict, start_transfer: dict, constraints: dict) -> dict:
    start = _parse_lnglat(str(constraints.get("start_location") or ""))
    if not start or not day_plan.get("days"):
        return day_plan
    target_id = start_transfer.get("to")
    if target_id and all(block.get("id") != target_id for block in day_plan.get("blocks", [])):
        return day_plan
    english = constraints.get("language") == "en"
    start_name = start_transfer.get("from_name") or ("Start point" if english else "起点")
    day_one = next((day for day in day_plan.get("days", []) if day.get("day_index") == 1), day_plan["days"][0])
    start_time = day_one.get("start_time") or constraints.get("daily_start_time") or "10:00"
    start_block = {
        "id": "start",
        "name": start_name,
        "category": "Start" if english else "起点",
        "type": "start",
        "icon": "S",
        "lng": start[0],
        "lat": start[1],
        "duration": 0,
        "price": 0,
        "unit_price": 0,
        "rating": None,
        "address": constraints.get("start_location_address") or start_name,
        "tags": ["Start point"] if english else ["起点"],
        "reason": "Trip starts here" if english else "本次路线起点",
        "recommendation": "",
        "day_index": 1,
        "start_time": start_time,
        "end_time": start_time,
        "time_note": "Start point" if english else "从这里出发",
        "is_start": True,
    }
    if any(block.get("id") == "start" for block in day_plan.get("blocks", [])):
        return day_plan

    connection = {**start_transfer, "day_index": 1}
    day_plan["blocks"] = [start_block, *day_plan.get("blocks", [])]
    day_plan["connections"] = [connection, *day_plan.get("connections", [])]
    day_one["blocks"] = [start_block, *day_one.get("blocks", [])]
    day_one["connections"] = [connection, *day_one.get("connections", [])]
    day_one["total_duration"] = int(day_one.get("total_duration") or 0)
    day_one["total_price"] = sum(block.get("price", 0) for block in day_one.get("blocks", []))
    return day_plan


def _apply_start_transfer_to_day_plan(day_plan: dict, minutes: int, constraints: dict) -> dict:
    # A local cross-district transit leg can easily exceed 90 minutes. Only
    # ignore extreme values that would represent intercity travel or bad data.
    if minutes <= 0 or minutes > 240:
        return day_plan
    shifted_objects = set()

    def shift_block(block: dict) -> None:
        if id(block) in shifted_objects or block.get("day_index") != 1:
            return
        if block.get("start_time"):
            block["start_time"] = _format_minutes(_parse_time_to_minutes(block["start_time"]) + minutes)
        if block.get("end_time"):
            block["end_time"] = _format_minutes(_parse_time_to_minutes(block["end_time"]) + minutes)
        shifted_objects.add(id(block))

    for block in day_plan.get("blocks", []):
        shift_block(block)

    for day in day_plan.get("days", []):
        if day.get("day_index") != 1:
            continue
        for block in day.get("blocks", []):
            shift_block(block)
        if day.get("end_time"):
            day["end_time"] = _format_minutes(_parse_time_to_minutes(day["end_time"]) + minutes)
        day["total_duration"] = int(day.get("total_duration") or 0) + minutes
        _trim_day_to_end_window(day_plan, day, constraints)
        break
    return day_plan


def _trim_day_to_end_window(day_plan: dict, day: dict, constraints: dict) -> None:
    end_limit = _parse_time_to_minutes(constraints.get("daily_end_time", "20:30")) + 15
    day_blocks = day.get("blocks") or []
    trip_days = max(1, int(constraints.get("trip_days") or 1))
    duration = int(constraints.get("daily_duration_minutes") or constraints.get("duration_minutes") or 0)
    min_visible_blocks = 4 if trip_days == 1 and duration >= 240 else 3

    def visible_block_count() -> int:
        return sum(1 for block in day_blocks if not block.get("is_start"))

    while (
        day_blocks
        and visible_block_count() > min_visible_blocks
        and _parse_time_to_minutes(day_blocks[-1].get("end_time", "00:00")) > end_limit
    ):
        removed = day_blocks.pop()
        removed_id = removed.get("id")
        day_plan["blocks"] = [block for block in day_plan.get("blocks", []) if block.get("id") != removed_id]
        day["connections"] = [
            conn for conn in day.get("connections", [])
            if conn.get("from") != removed_id and conn.get("to") != removed_id
        ]
        day_plan["connections"] = [
            conn for conn in day_plan.get("connections", [])
            if conn.get("from") != removed_id and conn.get("to") != removed_id
        ]
    if day_blocks:
        day["end_time"] = day_blocks[-1].get("end_time", day.get("start_time", ""))
    else:
        day["end_time"] = day.get("start_time", "")
    day["total_duration"] = max(0, _parse_time_to_minutes(day["end_time"]) - _parse_time_to_minutes(day.get("start_time", "00:00")))
    day["total_price"] = sum(block.get("price", 0) for block in day_blocks)


def _format_distance(distance_m: float) -> str:
    return f"{int(distance_m)}m" if distance_m < 1000 else f"{distance_m / 1000:.1f}km"


def _fit_analysis_lines(itinerary: dict, constraints: dict, english: bool = False) -> list[str]:
    blocks = itinerary.get("blocks", [])
    budget = constraints.get("budget")
    total_price = itinerary.get("total_price", 0)
    target_ratio = constraints.get("budget_target_ratio", 0.72)
    warnings = []
    for block in blocks:
        text = f"{block.get('name', '')} {block.get('category', '')} {' '.join(block.get('tags') or [])}"
        start = block.get("start_time") or ""
        hour = int(start.split(":", 1)[0]) if re.match(r"^\d{1,2}:", start) else None
        if hour is not None and hour < 17 and any(word in text for word in ["夜景", "酒吧", "夜市", "灯光", "演出"]):
            warnings.append(block.get("name", ""))

    if english:
        lines = ["\n### Fit Check"]
        if budget:
            utilization = total_price / max(budget, 1)
            if utilization < target_ratio - 0.2:
                lines.append(f"- Budget use is conservative at {utilization:.0%}; the richer option raises spending with dining/experience upgrades.")
            elif utilization <= 1:
                lines.append(f"- Budget use is within range at {utilization:.0%}.")
            else:
                lines.append(f"- This plan is over budget; use the value option if budget is strict.")
        lines.append("- Time fit passed: dining, entertainment and night-view stops are placed into matching windows." if not warnings else f"- Time warning: check {', '.join(warnings[:3])}.")
        return lines

    lines = ["\n### 方案自检"]
    if budget:
        utilization = total_price / max(budget, 1)
        if utilization < target_ratio - 0.2:
            lines.append(f"- 预算利用偏保守：当前约 {utilization:.0%}，可切换“预算充分/吃好玩好”提高餐饮、体验或夜间项目质量。")
        elif utilization <= 1:
            lines.append(f"- 预算利用合理：当前约 {utilization:.0%}，符合“{constraints.get('budget_level', 'balanced')}”预算策略。")
        else:
            lines.append("- 预算超出：如果预算刚性，建议切换“省钱轻量/性价比”方案。")
    if warnings:
        lines.append(f"- 时段警告：{', '.join(warnings[:3])} 可能仍需改到傍晚后。")
    else:
        lines.append("- 时段匹配通过：正餐、下午茶、娱乐和夜景已按更合理时间窗放置。")
    return lines


def _event_markdown_line(event: dict, english: bool = False) -> str:
    summary_key = "summary_en" if english else "summary"
    summary = (event.get(summary_key) or event.get("summary") or event.get("title") or ("Event" if english else "活动")).strip()
    summary = re.sub(r"\s+", " ", summary)[:130]
    url = event.get("url") or ""
    if url:
        return f"- {summary} ([link]({url}))" if english else f"- {summary}（[链接]({url})）"
    return f"- {summary}"


def _upgrade_markdown_line(item: dict, english: bool = False) -> str:
    summary_key = "summary_en" if english else "summary"
    title = item.get("title") or ("Upgrade" if english else "升级项")
    summary = (item.get(summary_key) or item.get("summary") or title).strip()
    summary = re.sub(r"\s+", " ", summary)[:150]
    cost = item.get("estimated_cost")
    if cost:
        return f"- {summary} ({'est.' if english else '预计'} ¥{cost})"
    return f"- {summary}"


def _local_explanation(itinerary: dict, alternatives: list[dict], constraints: dict) -> str:
    blocks = itinerary.get("blocks", [])
    names = " → ".join(block.get("name", "") for block in blocks)
    budget = constraints.get("budget")
    people = constraints.get("people_count") or 1
    prefs = _display_preferences(constraints.get("preferences") or ["综合体验"], constraints)
    if constraints.get("language") == "en":
        start_transfer = itinerary.get("start_transfer")
        lines = [
            f"## {_display_plan_name(itinerary.get('plan_name', 'Recommended Route'), constraints)}",
            f"Route: {names}",
            f"- Estimated duration: {itinerary.get('total_duration', 0)} min",
            f"- Estimated cost: ¥{itinerary.get('total_price', 0)} total for {people}",
            f"- Preference match: {prefs}",
        ]
        if start_transfer:
            lines.append(
                f"- Start access: {start_transfer.get('from_name')} → {start_transfer.get('to_name')}, "
                f"{start_transfer.get('mode')} about {start_transfer.get('time')} / {start_transfer.get('distance')}"
            )
        if budget:
            remain = budget - itinerary.get("total_price", 0)
            lines.append(f"- Budget: within ¥{budget}, about ¥{max(remain, 0)} left for optional upgrades.")
        if alternatives:
            lines.append("\n### Other Options")
            for alt in alternatives[:3]:
                lines.append(
                    f"- **{_display_plan_name(alt.get('plan_name', ''), constraints)}**: {len(alt.get('blocks', []))} stops, "
                    f"{alt.get('total_duration', 0)} min, ¥{alt.get('total_price', 0)}"
                )
        if itinerary.get("upgrade_suggestions"):
            lines.append("\n### Optional Upgrades")
            for item in itinerary["upgrade_suggestions"][:4]:
                lines.append(_upgrade_markdown_line(item, english=True))
        lines.append("\nYou can load this plan again from the chat card, switch styles on the right, or ask for less walking / better value / fewer queues.")
        return "\n".join(lines)

    start_transfer = itinerary.get("start_transfer")
    lines = [
        f"## {itinerary.get('plan_name', '综合路线')}",
        f"路线：{names}",
        f"- 预计总时长：{itinerary.get('total_duration', 0)} 分钟",
        f"- 预计总花费：¥{itinerary.get('total_price', 0)}（{people}人合计）",
        f"- 匹配偏好：{prefs}",
    ]
    if start_transfer:
        lines.append(
            f"- 起点接入：{start_transfer.get('from_name')} → {start_transfer.get('to_name')}，"
            f"{start_transfer.get('mode')}约{start_transfer.get('time')}，{start_transfer.get('distance')}"
        )
    if budget:
        remain = budget - itinerary.get("total_price", 0)
        lines.append(f"- 预算：控制在 ¥{budget} 内，约剩 ¥{max(remain, 0)} 可用于临时加餐或升级体验")
    if alternatives:
        lines.append("\n### 其他可选方案")
        for alt in alternatives[:3]:
            lines.append(
                f"- **{alt.get('plan_name')}**：{len(alt.get('blocks', []))} 个地点，"
                f"{alt.get('total_duration', 0)} 分钟，¥{alt.get('total_price', 0)}"
            )
    if itinerary.get("upgrade_suggestions"):
        lines.append("\n### 建议")
        for item in itinerary["upgrade_suggestions"][:4]:
            lines.append(_upgrade_markdown_line(item))
    lines.append("\n右侧可以切换不同风格方案，也可以继续要求“少走路 / 省钱 / 少排队 / 换餐厅”。")
    return "\n".join(lines)


def explain_node(state: PlannerState, llm) -> dict:
    _log("explain", "进入解释节点")

    itinerary = state.get("itinerary")
    if not itinerary:
        return {"messages": [AIMessage(content="抱歉，当前城市和条件下没有找到足够地点。可以放宽预算、换区域或增加偏好后再试。")]}

    constraints = state.get("constraints", {})
    alternatives = state.get("alternative_plans", [])
    content = _local_explanation(itinerary, alternatives, constraints)
    return {"messages": [AIMessage(content=content)]}


def _duration_for_category(category: str, name: str = "", tags: list[str] | None = None, address: str = "") -> int:
    text = " ".join([str(name or ""), str(category or ""), str(address or ""), *map(str, tags or [])])
    if any(keyword in text for keyword in ["商圈", "步行街", "商业街", "购物中心", "太古汇", "万象城", "K11", "天河城", "正佳", "北京路", "上下九", "市桥"]):
        return 120
    if any(keyword in text for keyword in ["广场", "古镇", "老街", "景区"]):
        return 95
    if category == "购物":
        return 105
    return {
        "咖啡": 35,
        "餐厅": 65,
        "甜品": 25,
        "景点": 45,
        "展览": 60,
        "公园": 40,
        "购物": 70,
        "夜景": 50,
        "娱乐": 90,
    }.get(category, 45)


def _default_unit_price(category: str, tags: list[str], name: str = "", address: str = "") -> int:
    if "免费" in tags:
        return 0
    text = " ".join([name, address, *map(str, tags)])
    name_rules = [
        (("长隆", "乐园", "动物世界", "水上乐园", "欢乐世界"), 260),
        (("广州塔", "观景台", "摩天轮"), 180),
        (("演唱会", "音乐节", "Livehouse", "livehouse", "剧场", "演出"), 180),
        (("密室", "剧本杀", "电竞", "电玩", "桌游"), 150),
        (("太古汇", "万象城", "K11", "天河城", "购物中心", "商场", "步行街"), 180),
        (("酒家", "粤菜", "火锅", "烧肉", "牛排", "私房菜", "茶楼"), 150),
    ]
    for keywords, default_cost in name_rules:
        if any(keyword in text for keyword in keywords):
            return default_cost
    return {
        "咖啡": 40,
        "餐厅": 150,
        "甜品": 35,
        "购物": 260,
        "夜景": 120,
        "景点": 50,
        "展览": 80,
        "公园": 0,
        "娱乐": 220,
    }.get(category, 30)


def _build_blocks(route: list[dict], people_count: int = 1) -> list[dict]:
    import json as _json

    blocks = []
    for poi in route:
        category = poi.get("category", "")
        tags = _json.loads(poi.get("tags", "[]")) if isinstance(poi.get("tags"), str) else poi.get("tags", [])
        review = poi.get("review") or {}
        review_content = review.get("content") if isinstance(review, dict) else ""
        unit_price = int(poi.get("avg_cost") or 0) or _default_unit_price(
            category,
            tags,
            str(poi.get("name") or ""),
            str(poi.get("address") or ""),
        )
        block = {
            "id": poi["id"],
            "name": poi["name"],
            "category": category,
            "type": _get_frontend_type(category),
            "icon": _get_category_icon(category),
            "lng": poi.get("lng"),
            "lat": poi.get("lat"),
            "duration": _duration_for_category(category, str(poi.get("name") or ""), tags, str(poi.get("address") or "")),
            "price": unit_price * people_count,
            "unit_price": unit_price,
            "rating": poi.get("rating", 0),
            "address": poi.get("address", ""),
            "tags": tags,
            "reason": " / ".join(tags[:3]) if tags else category,
            "recommendation": review_content or "",
        }
        blocks.append(block)
    return blocks


def _build_map_pois(all_pois: list[dict], route: list[dict], people_count: int = 1, limit: int = 28) -> list[dict]:
    route_ids = {poi.get("id") for poi in route}
    route_names = {_normalize_name(poi.get("name", "")) for poi in route}
    category_quota = {
        "景点": 5,
        "展览": 4,
        "公园": 4,
        "餐厅": 5,
        "咖啡": 4,
        "甜品": 3,
        "购物": 4,
        "娱乐": 4,
        "夜景": 4,
    }
    counts: dict[str, int] = {}

    candidates = []
    for poi in all_pois:
        if poi.get("id") in route_ids or _normalize_name(poi.get("name", "")) in route_names:
            continue
        if poi.get("lng") is None or poi.get("lat") is None:
            continue
        category = poi.get("category", "")
        score = poi.get("_score", 0) + float(poi.get("rating") or 0) * 0.08
        if category in {"景点", "展览", "公园", "夜景", "娱乐"}:
            score += 0.25
        candidates.append((score, poi))

    candidates.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for _, poi in candidates:
        category = poi.get("category", "其他")
        if counts.get(category, 0) >= category_quota.get(category, 3):
            continue
        selected.append(poi)
        counts[category] = counts.get(category, 0) + 1
        if len(selected) >= limit:
            break

    blocks = _build_blocks(selected, people_count)
    for block in blocks:
        block["is_auxiliary"] = True
        block["reason"] = f"周边可替换点：{block.get('reason') or block.get('category', '')}"
    return blocks


def _normalize_name(name: str) -> str:
    return "".join(str(name or "").lower().split())


def _split_into_days(blocks: list[dict], connections: list[dict], constraints: dict, guide_signals: dict | None = None) -> dict:
    trip_days = max(1, int(constraints.get("trip_days") or 1))
    if not blocks:
        return {"blocks": [], "connections": [], "days": []}

    from services.guide_service import infer_food_time_slot

    daily_start = constraints.get("daily_start_time", "10:00")
    if trip_days > 1 and daily_start == "10:00":
        daily_start = "09:30"
    end_time = constraints.get("daily_end_time", "20:30")
    start_min = _parse_time_to_minutes(daily_start)
    end_min = _parse_time_to_minutes(end_time)
    daily_budget = max(240, end_min - start_min)

    days = []
    flat_blocks = []
    flat_connections = []
    block_index = 0
    conn_index = 0

    for day_index in range(1, trip_days + 1):
        remaining_blocks = len(blocks) - block_index
        remaining_days = trip_days - day_index + 1
        if remaining_blocks <= 0:
            break
        target_count = max(1, math_ceil(remaining_blocks / remaining_days))
        current_min = start_min if day_index > 1 or trip_days == 1 else _parse_time_to_minutes(constraints.get("daily_start_time", "10:00"))
        day_blocks = []
        day_connections = []

        while block_index < len(blocks) and len(day_blocks) < target_count:
            block = {**blocks[block_index]}
            block["day_index"] = day_index
            aligned_min = _align_block_start_time(block, current_min, infer_food_time_slot(block))
            min_floor = 4 if trip_days == 1 and daily_budget >= 240 else 3
            min_day_stops = max(min_floor, min(target_count, daily_budget // 95))
            if day_blocks and len(day_blocks) >= min_day_stops and aligned_min + block.get("duration", 60) > end_min + 45:
                break
            current_min = aligned_min
            block["start_time"] = _format_minutes(current_min)
            current_min += block.get("duration", 60)
            block["end_time"] = _format_minutes(current_min)
            block["time_note"] = _time_note_for_block(block, infer_food_time_slot(block), guide_signals or {})
            day_blocks.append(block)
            flat_blocks.append(block)

            if block_index < len(connections):
                conn = {**connections[block_index], "day_index": day_index}
                travel_min = _connection_minutes(conn)
                if len(day_blocks) < target_count and current_min + travel_min <= start_min + daily_budget + 60:
                    day_connections.append(conn)
                    flat_connections.append(conn)
                    current_min += travel_min
                    conn_index += 1
            block_index += 1

        day_price = sum(block.get("price", 0) for block in day_blocks)
        day_duration = max(0, current_min - start_min)
        days.append({
            "day_index": day_index,
            "title": f"Day {day_index}",
            "date_label": _date_label_for_day(constraints.get("time_slot"), day_index),
            "start_time": _format_minutes(start_min),
            "end_time": _format_minutes(current_min),
            "total_duration": day_duration,
            "total_price": day_price,
            "blocks": day_blocks,
            "connections": day_connections,
            "guide_strategy": (guide_signals or {}).get("strategy", []),
        })

    return {"blocks": flat_blocks, "connections": flat_connections, "days": days}


def _align_block_start_time(block: dict, current_min: int, food_slot: str | None) -> int:
    text = f"{block.get('name', '')} {block.get('category', '')} {' '.join(block.get('tags') or [])}"
    if block.get("category") == "夜景" or any(word in text for word in ["夜景", "夜市", "酒吧", "灯光", "演出", "音乐节", "Livehouse", "livehouse"]):
        return max(current_min, 18 * 60 + 15)
    if block.get("category") == "娱乐" or any(word in text for word in ["游戏", "电竞", "电玩", "桌游", "密室", "剧本杀", "网咖", "网吧"]):
        return max(current_min, 14 * 60)
    if block.get("category") == "购物" and current_min < 11 * 60:
        return max(current_min, 11 * 60)
    if food_slot == "morning":
        return max(current_min, 9 * 60)
    if food_slot == "afternoon":
        return max(current_min, 14 * 60 + 15)
    if food_slot == "dinner":
        return max(current_min, 17 * 60 + 30)
    if food_slot == "meal":
        if current_min < 11 * 60:
            return max(current_min, 11 * 60 + 15)
        if 14 * 60 < current_min < 17 * 60 + 15:
            return 17 * 60 + 15
    return current_min


def _time_note_for_block(block: dict, food_slot: str | None, guide_signals: dict) -> str:
    category = block.get("category")
    text = f"{block.get('name', '')} {category} {' '.join(block.get('tags') or [])}"
    if category == "夜景" or any(word in text for word in ["夜景", "夜市", "酒吧", "灯光", "演出", "音乐节", "Livehouse", "livehouse"]):
        return "傍晚后体验更合理"
    if category == "娱乐" or any(word in text for word in ["游戏", "电竞", "电玩", "桌游", "密室", "剧本杀"]):
        return "适合下午或晚间的娱乐段"
    if category in {"景点", "公园"} and any(word in text for word in ["山", "徒步", "森林", "公园", "湖", "步道"]):
        return "上午体力或户外段"
    if category == "购物":
        return "下午到傍晚更适合逛街"
    if food_slot == "morning":
        return "早茶/早餐时段"
    if food_slot == "afternoon":
        return "适合作为下午茶或休息点"
    if food_slot == "dinner":
        return "晚餐时段更合理"
    if food_slot == "meal":
        return "避开正峰的正餐安排"
    return ""


def math_ceil(value: float) -> int:
    return int(-(-value // 1))


def _parse_time_to_minutes(value: str) -> int:
    match = re.match(r"(\d{1,2}):(\d{2})", value or "")
    if not match:
        return 10 * 60
    return int(match.group(1)) * 60 + int(match.group(2))


def _format_minutes(value: int) -> str:
    value = max(0, value)
    return f"{(value // 60) % 24:02d}:{value % 60:02d}"


def _connection_minutes(conn: dict) -> int:
    duration = conn.get("duration_minutes")
    if isinstance(duration, (int, float)) and duration > 0:
        return int(duration)

    text = str(conn.get("time", "") or "")
    hour_match = re.search(r"(\d+)小时(?:(\d+)分钟)?", text)
    if hour_match:
        return int(hour_match.group(1)) * 60 + int(hour_match.group(2) or 0)
    minute_match = re.search(r"(\d+)分钟", text)
    if minute_match:
        return int(minute_match.group(1))
    en_hour_match = re.search(r"(\d+)\s*(?:h|hour|hours)(?:\s*(\d+)\s*(?:m|min|mins|minute|minutes))?", text, re.I)
    if en_hour_match:
        return int(en_hour_match.group(1)) * 60 + int(en_hour_match.group(2) or 0)
    en_minute_match = re.search(r"(\d+)\s*(?:m|min|mins|minute|minutes)", text, re.I)
    if en_minute_match:
        return int(en_minute_match.group(1))
    return 15


def _date_label_for_day(time_slot: str | None, day_index: int) -> str:
    text = time_slot or ""
    range_label = _date_label_from_range(_extract_date_range_parts(text), day_index)
    if range_label:
        return range_label
    single_label = _single_date_from_text(text)
    if single_label:
        try:
            month, day = [int(part) for part in re.findall(r"\d+", single_label)[:2]]
            current = date(CURRENT_DATE.year, month, day) + timedelta(days=day_index - 1)
            return f"{current.month}月{current.day}日"
        except (ValueError, TypeError):
            return single_label if day_index == 1 else f"第{day_index}天"
    if "周末" in text:
        return "周六" if day_index == 1 else "周日" if day_index == 2 else f"第{day_index}天"
    return f"第{day_index}天"


def _get_frontend_type(category: str) -> str:
    mapping = {
        "咖啡": "cafe",
        "餐厅": "food",
        "景点": "scenic",
        "展览": "exhibition",
        "公园": "park",
        "购物": "shopping",
        "甜品": "food",
        "夜景": "entertainment",
        "娱乐": "entertainment",
    }
    return mapping.get(category, "scenic")


def _format_connection_time(minutes: int) -> str:
    minutes = max(1, int(minutes))
    return f"{minutes}分钟" if minutes < 60 else f"{minutes // 60}小时{minutes % 60}分钟"


def _estimate_transit_minutes_for_distance(distance_m: int | float | None) -> int:
    if not distance_m:
        return 18
    distance_m = float(distance_m)
    if distance_m <= 1600:
        return max(8, round(distance_m / 75))
    if distance_m <= 5000:
        return max(14, round(distance_m / 360) + 7)
    return max(24, round(distance_m / 430) + 12)


def _use_transit_for_long_walk(mode: str, distance_m: int | float | None, minutes: int | None) -> bool:
    if mode != "walking":
        return False
    if minutes is not None and minutes > 20:
        return True
    return bool(distance_m and distance_m > 1600)


def _build_connections(
    route: list[dict],
    matrix: dict = None,
    mode: str = "walking",
    constraints: dict | None = None,
    include_details: bool = True,
) -> list[dict]:
    base_mode_label = {"walking": "步行", "bicycling": "骑行", "driving": "驾车", "transit": "公共交通"}.get(mode, "步行")
    base_shape_mode = mode if mode in {"walking", "bicycling", "driving"} else None
    constraints = constraints or {}
    connections = []
    try:
        from tools.amap import fetch_direction_polyline, fetch_transit_plan
    except Exception:
        fetch_direction_polyline = None
        fetch_transit_plan = None
    for i in range(len(route) - 1):
        from_id = route[i]["id"]
        to_id = route[i + 1]["id"]
        key = (from_id, to_id)
        dist_m = None
        minutes = None

        if matrix and key in matrix:
            dist_m = matrix[key]["distance_m"]
            dur_s = matrix[key]["duration_s"]
            distance = f"{dist_m}m" if dist_m < 1000 else f"{dist_m / 1000:.1f}km"
            minutes = max(1, dur_s // 60)
            time = _format_connection_time(minutes)
        else:
            distance = "未知"
            time = "未知"

        leg_mode = mode
        leg_mode_label = base_mode_label
        leg_shape_mode = base_shape_mode
        if _use_transit_for_long_walk(mode, dist_m, minutes):
            leg_mode = "transit"
            leg_mode_label = "公共交通"
            leg_shape_mode = None
            minutes = _estimate_transit_minutes_for_distance(dist_m)
            time = _format_connection_time(minutes)

        connection = {
            "from": from_id,
            "to": to_id,
            "from_name": route[i].get("name"),
            "to_name": route[i + 1].get("name"),
            "from_lng": route[i].get("lng"),
            "from_lat": route[i].get("lat"),
            "to_lng": route[i + 1].get("lng"),
            "to_lat": route[i + 1].get("lat"),
            "distance": distance,
            "time": time,
            "duration_minutes": minutes,
            "distance_m": dist_m,
            "mode": leg_mode_label,
            "city": constraints.get("adcode") or constraints.get("city") or "",
        }
        if not include_details:
            connections.append(connection)
            continue

        origin = f"{route[i].get('lng')},{route[i].get('lat')}"
        destination = f"{route[i + 1].get('lng')},{route[i + 1].get('lat')}"
        if leg_mode == "transit" and fetch_transit_plan:
            try:
                transit_detail = fetch_transit_plan(
                    origin,
                    destination,
                    str(constraints.get("adcode") or constraints.get("city") or ""),
                    str(constraints.get("adcode") or constraints.get("city") or ""),
                )
            except Exception:
                transit_detail = None
            if transit_detail:
                connection["transit_detail"] = transit_detail
                if transit_detail.get("duration"):
                    connection["time"] = transit_detail["duration"]
                if transit_detail.get("route_path"):
                    connection["route_path"] = transit_detail["route_path"]
                    connection["route_path_source"] = "amap_transit"
        elif leg_shape_mode and fetch_direction_polyline:
            path = fetch_direction_polyline(origin, destination, leg_shape_mode)
            if path:
                connection["route_path"] = path
        connections.append(connection)
    return connections


def _get_category_icon(category: str) -> str:
    icons = {
        "咖啡": "☕",
        "餐厅": "🍽",
        "景点": "📍",
        "展览": "🖼",
        "公园": "🌿",
        "购物": "🛍",
        "甜品": "🍰",
        "夜景": "🌃",
        "娱乐": "🎮",
    }
    return icons.get(category, "📍")
