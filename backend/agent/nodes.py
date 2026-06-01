import json
import re
from langchain_core.messages import HumanMessage, AIMessage

from .state import PlannerState
from .context import build_context


def _log(node: str, msg: str):
    print(f"[{node}] {msg}")


INTENT_PROMPT = """你是“Roam 漫游”的意图识别模块。你的任务是把用户的自然语言出行需求解析成结构化字段。

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
  "preferences": ["美食", "咖啡", "看展", "自然", "购物", "亲子", "夜景", "探店", "拍照", "历史", "热闹", "爬山", "户外", "游戏", "运动"]；没提到则为 null,
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

ASK_PROMPT = """你是“Roam 漫游”。现在还缺少生成可执行路线的关键信息。

已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

缺失信息：{missing}

请最多问两个短问题，语气直接，不要重复已知信息，不要添加推荐示例。"""

CHAT_PROMPT = """你是“Roam”，专注于多目的地路线规划。
请用 2 句话以内回复，并自然引导用户给出城市/区域、时间、人数、预算和偏好。"""


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

PREFERENCE_PATTERNS = [
    (("吃喝玩乐", "都要", "全都要"), ["美食", "咖啡", "购物", "夜景", "探店"]),
    (("逛街", "商场", "商圈", "买东西", "购物"), ["购物"]),
    (("热闹", "热门", "人气", "烟火气"), ["热闹", "购物", "夜景"]),
    (("吃好", "美食", "吃饭", "餐厅", "小吃", "本地菜", "好吃", "早茶", "茶点"), ["美食"]),
    (("咖啡", "探店", "下午茶"), ["咖啡", "探店"]),
    (("看展", "展览", "美术馆", "博物馆", "艺术"), ["看展"]),
    (("自然", "公园", "散步", "湖", "山", "湿地", "园林", "园子"), ["自然"]),
    (("爬山", "登山", "徒步", "山野", "森林", "露营", "户外", "hiking", "hike", "trekking", "outdoor"), ["爬山", "户外", "自然"]),
    (("运动", "健身", "骑行", "攀岩", "篮球", "羽毛球", "running", "cycling", "sports", "climbing"), ["运动", "户外"]),
    (("亲子", "带娃", "小朋友", "父母", "老人"), ["亲子"]),
    (("夜景", "酒吧", "晚上", "夜生活"), ["夜景"]),
    (("打游戏", "游戏", "电竞", "电玩", "桌游", "密室", "剧本杀", "网咖", "网吧", "game", "gaming", "esports", "arcade", "board game"), ["游戏", "热闹"]),
    (("拍照", "出片", "打卡"), ["拍照"]),
    (("历史", "老街", "古镇", "文化"), ["历史"]),
    (("food", "eat", "restaurant", "local cuisine", "snack", "brunch"), ["美食"]),
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
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return None


def _extract_people_count(message: str) -> int | None:
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


def _extract_trip_days(message: str) -> int | None:
    lower_message = message.lower()
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


def _extract_time_slot(message: str) -> str | None:
    message = re.sub(r"-?\d{2,3}\.\d+\s*[,，]\s*-?\d{1,2}\.\d+", "", message)
    range_match = re.search(
        r"(\d{1,2})[./月](\d{1,2})(?:日|号)?\s*(?:-|~|至|到)\s*(?:(\d{1,2})[./月])?(\d{1,2})(?:日|号)?",
        message,
    )
    if range_match:
        start_month, start_day, end_month, end_day = range_match.groups()
        end_month = end_month or start_month
        return f"{int(start_month)}月{int(start_day)}日-{int(end_month)}月{int(end_day)}日"

    single_match = re.search(r"(\d{1,2})[./月](\d{1,2})(?:日|号)?", message)
    parts = []
    if single_match:
        parts.append(f"{int(single_match.group(1))}月{int(single_match.group(2))}日")

    days = _extract_trip_days(message)
    if days and days > 1:
        parts.append(f"{days}天")

    for token in ["今天", "明天", "后天", "周末", "周六", "周日", "工作日", "一天", "两天", "三天", "半天"]:
        if token in message and token not in parts:
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
    return None


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
    if "不排队" in message or "少排队" in message or "别排队" in message or "avoid queues" in lower_message or "less queue" in lower_message:
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

    city = _extract_city(message)
    if city:
        data["location"] = city

    budget = _extract_budget(message)
    if budget is not None:
        data["budget"] = budget

    people_count = _extract_people_count(message)
    if people_count is not None:
        data["people_count"] = people_count

    trip_days = _extract_trip_days(message)
    if trip_days is not None:
        data["trip_days"] = trip_days

    time_slot = _extract_time_slot(message)
    if time_slot:
        data["time_slot"] = time_slot

    start_location = _extract_start_location(message)
    if start_location:
        data["start_location"] = start_location

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
    elif any(key in data for key in ["location", "budget", "preferences", "people_count", "time_slot", "trip_days"]):
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

    for field in ["location", "budget", "preferences", "people_count", "time_slot"]:
        val = data.get(field)
        if val in (None, "null", ""):
            val = rule_data.get(field)
        if val not in (None, "null", ""):
            result[field] = val

    for field in ["trip_days", "start_location", "language"]:
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
        "time_slot": state.get("time_slot"),
        "trip_days": 1,
        "daily_start_time": "10:00",
        "start_location": None,
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
    if rule_data.get("language"):
        result["language"] = rule_data["language"]
    if not result.get("duration_minutes"):
        result["duration_minutes"] = _estimate_duration_minutes(result.get("time_slot") or message)
    if rule_data.get("preferences"):
        result["preferences"] = _merge_unique(list(result.get("preferences") or []) + rule_data["preferences"])
    result["trip_days"] = _estimate_trip_days(result.get("time_slot") or message, result.get("duration_minutes"), result.get("trip_days"))
    result["persona_strategy"] = _infer_persona_strategy(result.get("preferences") or [])
    result["daily_start_time"] = _infer_daily_start_time(message, result.get("time_slot"), result["trip_days"])
    if set(result.get("preferences") or []) & {"爬山", "户外"} and not re.search(r"\d{1,2}[:：点]", message):
        result["daily_start_time"] = "08:30"
    late_keywords = ["夜景", "酒吧", "演出", "音乐节", "晚上", "电竞", "游戏", "密室", "剧本杀", "夜市"]
    result["daily_end_time"] = "22:00" if any(word in message for word in late_keywords) else "20:30"
    result["time_strategy"] = _build_time_strategy(result)
    if "排队" in message:
        result["queue_tolerance"] = 1
        result["avoid_tags"] = _merge_unique(list(result.get("avoid_tags") or []) + ["排队"])
    if any(word in message for word in ["小红书", "种草", "攻略", "避雷", "网红", "出片"]):
        result["ugc_source"] = "xhs"
    if any(word in message for word in ["少走路", "轻松", "别太累"]):
        result["pace"] = "relaxed"
        result["distance_weight_boost"] = 2.2
    if set(result.get("preferences") or []) & {"爬山", "户外"}:
        result["pace"] = "active"
    if any(word in message for word in ["紧凑", "赶时间", "多去几个"]):
        result["pace"] = "intense"
    return result


def _estimate_duration_minutes(time_text: str) -> int | None:
    text = time_text or ""
    range_match = re.search(r"(\d{1,2})月(\d{1,2})日-(?:(\d{1,2})月)?(\d{1,2})日", text)
    if range_match:
        start_month, start_day, end_month, end_day = range_match.groups()
        end_month = end_month or start_month
        if int(start_month) == int(end_month):
            days = max(1, int(end_day) - int(start_day) + 1)
            return min(days * 540, 14 * 540)
        return 2 * 540
    explicit_days = _extract_trip_days(text)
    if explicit_days:
        return explicit_days * 540
    if "三天" in text:
        return 3 * 540
    if "两天" in text or "2天" in text:
        return 2 * 540
    if "一天" in text or "一日" in text or "整天" in text:
        return 540
    if "半天" in text or "上午" in text or "下午" in text or "晚上" in text:
        return 240
    return None


def _estimate_trip_days(time_text: str, duration_minutes: int | None, existing: int | None = None) -> int:
    if existing:
        return max(1, min(int(existing), 14))
    text = time_text or ""
    range_match = re.search(r"(\d{1,2})月(\d{1,2})日-(?:(\d{1,2})月)?(\d{1,2})日", text)
    if range_match:
        start_month, start_day, end_month, end_day = range_match.groups()
        end_month = end_month or start_month
        if int(start_month) == int(end_month):
            return max(1, min(int(end_day) - int(start_day) + 1, 14))
        return 2
    explicit_days = _extract_trip_days(text)
    if explicit_days:
        return explicit_days
    if duration_minutes:
        return max(1, min(round(duration_minutes / 540), 14))
    return 1


def _build_time_strategy(constraints: dict) -> dict:
    trip_days = constraints.get("trip_days") or 1
    start_time = constraints.get("daily_start_time", "10:00")
    end_time = constraints.get("daily_end_time", "20:30")
    time_slot = constraints.get("time_slot") or "未指定"
    persona = constraints.get("persona_strategy") or _infer_persona_strategy(constraints.get("preferences") or [])
    if constraints.get("language") == "en":
        if trip_days > 1:
            note = f"{trip_days}-day itinerary split by {start_time}-{end_time}; the first day starts slightly lighter to avoid overloading arrival time."
        elif any(word in str(time_slot) for word in ["周末", "周六", "周日"]):
            note = f"Weekend plan starts around {start_time}; popular restaurants are shifted toward brunch or afternoon tea to reduce queues."
        else:
            note = f"When the exact time is unclear, the plan starts around {start_time} and keeps room for lunch, coffee and evening flexibility."
    elif trip_days > 1:
        note = f"{trip_days}天行程按每天{start_time}-{end_time}拆分，第一天略晚启动，避免到达日过满。"
    elif any(word in str(time_slot) for word in ["周末", "周六", "周日"]):
        note = f"周末默认{start_time}出发，热门餐饮尽量错峰到早午餐或下午茶。"
    else:
        note = f"时间不明确时默认{start_time}出发，保留午餐、下午茶和晚间弹性。"
    if persona.get("time_note"):
        note = f"{note} {persona['time_note']}"
    return {
        "daily_start_time": start_time,
        "daily_end_time": end_time,
        "trip_days": trip_days,
        "note": note,
        "persona": persona,
    }


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
    return {
        "name": "综合探索型",
        "time_note": "按景点、正餐、休息、体验和夜间活动组合，避免模板化堆点。",
        "category_order": ["景点", "展览", "餐厅", "咖啡", "购物", "夜景"],
    }


def collect_data_node(state: PlannerState, llm) -> dict:
    """解析约束、查询 POI、补全评价，支持修改逻辑。"""
    _log("collect_data", "进入数据收集节点")

    from services.intent_parser import parse_constraints, resolve_area
    from services.poi_service import search_or_fetch_pois
    from services.review_service import enrich_reviews
    from services.event_service import fetch_city_event_signals
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

    area_info = resolve_area(constraints)
    _log("collect_data", f"区域: {area_info}")
    if area_info.get("adcode"):
        constraints["adcode"] = area_info["adcode"]
    if area_info.get("resolved_name") and not constraints.get("resolved_name"):
        constraints["resolved_name"] = area_info["resolved_name"]

    city = constraints.get("city") or "杭州"
    preferences = constraints.get("preferences", [])
    budget = constraints.get("budget")
    people_count = constraints.get("people_count") or 1
    max_cost = (budget / people_count) * 0.85 if budget else None

    poi_limit = min(42, max(18, int(constraints.get("trip_days") or 1) * 8))
    pois = search_or_fetch_pois(
        city,
        preferences,
        max_cost,
        limit=poi_limit,
        area=constraints.get("area"),
        adcode=area_info.get("adcode"),
        center=area_info.get("center"),
    )

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

    should_fetch_events = (
        int(constraints.get("trip_days") or 1) > 1
        or any(word in str(constraints.get("time_slot", "")) for word in ["周末", "周六", "周日"])
        or any(word in last_message for word in ["活动", "音乐节", "演出", "市集", "展览"])
    )
    event_suggestions = fetch_city_event_signals(city, constraints.get("time_slot"), preferences) if should_fetch_events else []
    if event_suggestions:
        _log("collect_data", f"找到 {len(event_suggestions)} 条活动信号")

    should_build_guide = bool(
        constraints.get("ugc_source") == "xhs"
        or any(word in last_message.lower() for word in ["小红书", "攻略", "避雷", "网红", "xhs", "xiaohongshu"])
        or any(pref in preferences for pref in ["美食", "咖啡", "探店", "热闹"])
    )
    guide_signals = build_city_guide(city, preferences) if should_build_guide else {}
    if guide_signals:
        constraints["guide_strategy"] = guide_signals.get("strategy", [])
        _log("collect_data", f"形成攻略信号 {len(guide_signals.get('snippets', []))} 条")

    return {
        "constraints": constraints,
        "candidate_pois": pois,
        "area_info": area_info,
        "event_suggestions": event_suggestions,
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
    area_center = area_info.get("center")

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
        max_stops = 7 if dist_boost <= 1.5 else 6
    elif trip_days == 1 and duration_minutes and duration_minutes >= 300:
        max_stops = 6 if dist_boost <= 1.5 else 5
    elif duration_minutes and duration_minutes >= 900:
        max_stops = 7
    elif duration_minutes and duration_minutes >= 720:
        max_stops = 6
    elif duration_minutes and duration_minutes >= 360:
        max_stops = 5
    else:
        max_stops = 4 if dist_boost > 1.5 else 5
    if constraints.get("pace") == "intense":
        max_stops = max(max_stops, 8 if trip_days == 1 else 6)
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
    guide_signals = state.get("guide_signals", {})

    def to_itinerary(plan: dict) -> dict:
        blocks = _build_blocks(plan["route"], people_count)
        connections = _build_connections(plan["route"], matrix, transport_mode)
        day_plan = _split_into_days(blocks, connections, constraints, guide_signals)
        return {
            "blocks": day_plan["blocks"],
            "connections": day_plan["connections"],
            "days": day_plan["days"],
            "total_duration": plan["score"].get("total_duration_s", 0) // 60,
            "total_price": plan["score"].get("total_cost", 0),
            "score": plan["score"].get("route_score", 0),
            "plan_name": _display_plan_name(plan["name"], constraints),
            "style": plan.get("style", plan["name"]),
            "highlights": _display_highlights(plan.get("highlights", []), constraints),
            "total_distance": plan["score"].get("total_distance_m", 0),
            "time_plan": constraints.get("time_strategy", {}),
            "event_suggestions": event_suggestions,
            "guide_signals": guide_signals,
        }

    itinerary = to_itinerary(plans[0])
    alternatives = [to_itinerary(plan) for plan in plans[1:]]
    itinerary["alternatives"] = alternatives

    return {
        "itinerary": itinerary,
        "alternative_plans": alternatives,
    }


def _local_explanation(itinerary: dict, alternatives: list[dict], constraints: dict) -> str:
    blocks = itinerary.get("blocks", [])
    names = " → ".join(block.get("name", "") for block in blocks)
    budget = constraints.get("budget")
    people = constraints.get("people_count") or 1
    prefs = "、".join(constraints.get("preferences") or ["综合体验"])
    if constraints.get("language") == "en":
        lines = [
            f"## {itinerary.get('plan_name', 'Recommended Route')}",
            f"Route: {names}",
            f"- Estimated duration: {itinerary.get('total_duration', 0)} min",
            f"- Estimated cost: ¥{itinerary.get('total_price', 0)} total for {people}",
            f"- Preference match: {prefs}",
            f"- Strategy profile: {(constraints.get('persona_strategy') or {}).get('name', 'Balanced explorer')}",
            f"- Time strategy: {constraints.get('time_strategy', {}).get('note', 'Split by available time windows')}",
        ]
        if budget:
            remain = budget - itinerary.get("total_price", 0)
            lines.append(f"- Budget check: budget ¥{budget}, remaining about ¥{max(remain, 0)}")
        if alternatives:
            lines.append("\n### Other Options")
            for alt in alternatives[:3]:
                lines.append(
                    f"- **{alt.get('plan_name')}**: {len(alt.get('blocks', []))} stops, "
                    f"{alt.get('total_duration', 0)} min, ¥{alt.get('total_price', 0)}"
                )
        if itinerary.get("event_suggestions"):
            lines.append("\n### Recent Event Signals")
            for event in itinerary["event_suggestions"][:3]:
                lines.append(f"- **{event.get('title', 'Event')}**: {event.get('summary', '')[:80]}")
        lines.append("\nYou can load this plan again from the chat card, switch styles on the right, or ask for less walking / better value / fewer queues.")
        return "\n".join(lines)

    lines = [
        f"## {itinerary.get('plan_name', '综合路线')}",
        f"路线：{names}",
        f"- 预计总时长：{itinerary.get('total_duration', 0)} 分钟",
        f"- 预计总花费：¥{itinerary.get('total_price', 0)}（{people}人合计）",
        f"- 匹配偏好：{prefs}",
        f"- 人群策略：{(constraints.get('persona_strategy') or {}).get('name', '综合探索型')}",
        f"- 时间策略：{constraints.get('time_strategy', {}).get('note', '按可用时间拆分安排')}",
    ]
    if budget:
        remain = budget - itinerary.get("total_price", 0)
        lines.append(f"- 预算判断：预算 ¥{budget}，预计剩余 ¥{max(remain, 0)}")
    if alternatives:
        lines.append("\n### 其他可选方案")
        for alt in alternatives[:3]:
            lines.append(
                f"- **{alt.get('plan_name')}**：{len(alt.get('blocks', []))} 个地点，"
                f"{alt.get('total_duration', 0)} 分钟，¥{alt.get('total_price', 0)}"
            )
    if itinerary.get("event_suggestions"):
        lines.append("\n### 近期活动信号")
        for event in itinerary["event_suggestions"][:3]:
            lines.append(f"- **{event.get('title', '活动')}**：{event.get('summary', '')[:80]}")
    lines.append("\n右侧可以切换不同风格方案，也可以继续要求“少走路 / 省钱 / 少排队 / 换餐厅”。")
    return "\n".join(lines)


def explain_node(state: PlannerState, llm) -> dict:
    _log("explain", "进入解释节点")

    itinerary = state.get("itinerary")
    if not itinerary:
        return {"messages": [AIMessage(content="抱歉，当前城市和条件下没有找到足够地点。可以放宽预算、换区域或增加偏好后再试。")]}

    blocks = itinerary.get("blocks", [])
    route_desc = []
    for i, block in enumerate(blocks, 1):
        cost = block.get("unit_price", block.get("price", 0))
        cost_str = f"¥{cost}/人" if cost > 0 else "免费"
        route_desc.append(f"{i}. {block['name']} ({block.get('category', '')}, {cost_str})")

    route_text = "\n".join(route_desc)
    constraints = state.get("constraints", {})
    alternatives = state.get("alternative_plans", [])
    alt_text = "\n".join(
        f"- {alt.get('plan_name')}: {alt.get('total_duration')}分钟，¥{alt.get('total_price')}"
        for alt in alternatives[:3]
    )

    prompt = f"""你是“Roam 漫游”，请解释这次路线规划。

用户偏好：{constraints.get('preferences', [])}
人数：{constraints.get('people_count', 1)}
总预算：{constraints.get('budget', '未知')}
时间：{constraints.get('time_slot', '未知')}

主路线：
{route_text}

主路线总时间：{itinerary.get('total_duration', 0)}分钟
主路线总花费：¥{itinerary.get('total_price', 0)}

备选方案：
{alt_text}

请输出 Markdown，包含：
1. 主方案特点
2. 为什么这样安排
3. 预算和时间是否满足
4. 简短说明还有哪些备选风格

不要编造不存在的地点或价格。"""

    content = _local_explanation(itinerary, alternatives, constraints)
    return {"messages": [AIMessage(content=content)]}


def _duration_for_category(category: str) -> int:
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


def _default_unit_price(category: str, tags: list[str]) -> int:
    if "免费" in tags:
        return 0
    return {
        "咖啡": 40,
        "餐厅": 110,
        "甜品": 35,
        "购物": 180,
        "夜景": 120,
        "景点": 40,
        "展览": 50,
        "公园": 0,
        "娱乐": 120,
    }.get(category, 30)


def _build_blocks(route: list[dict], people_count: int = 1) -> list[dict]:
    import json as _json

    blocks = []
    for poi in route:
        category = poi.get("category", "")
        tags = _json.loads(poi.get("tags", "[]")) if isinstance(poi.get("tags"), str) else poi.get("tags", [])
        unit_price = int(poi.get("avg_cost") or 0) or _default_unit_price(category, tags)
        block = {
            "id": poi["id"],
            "name": poi["name"],
            "category": category,
            "type": _get_frontend_type(category),
            "icon": _get_category_icon(category),
            "duration": _duration_for_category(category),
            "price": unit_price * people_count,
            "unit_price": unit_price,
            "rating": poi.get("rating", 0),
            "address": poi.get("address", ""),
            "tags": tags,
            "reason": " / ".join(tags[:3]) if tags else category,
        }
        blocks.append(block)
    return blocks


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
            current_min = _align_block_start_time(block, current_min, infer_food_time_slot(block))
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
    text = conn.get("time", "")
    hour_match = re.search(r"(\d+)小时(?:(\d+)分钟)?", text)
    if hour_match:
        return int(hour_match.group(1)) * 60 + int(hour_match.group(2) or 0)
    minute_match = re.search(r"(\d+)分钟", text)
    if minute_match:
        return int(minute_match.group(1))
    return 15


def _date_label_for_day(time_slot: str | None, day_index: int) -> str:
    text = time_slot or ""
    range_match = re.search(r"(\d{1,2})月(\d{1,2})日-(?:(\d{1,2})月)?(\d{1,2})日", text)
    if range_match:
        month, start_day, _, _ = range_match.groups()
        return f"{int(month)}月{int(start_day) + day_index - 1}日"
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


def _build_connections(route: list[dict], matrix: dict = None, mode: str = "walking") -> list[dict]:
    mode_label = {"walking": "步行", "bicycling": "骑行", "driving": "驾车", "transit": "公共交通"}.get(mode, "步行")
    connections = []
    for i in range(len(route) - 1):
        from_id = route[i]["id"]
        to_id = route[i + 1]["id"]
        key = (from_id, to_id)

        if matrix and key in matrix:
            dist_m = matrix[key]["distance_m"]
            dur_s = matrix[key]["duration_s"]
            distance = f"{dist_m}m" if dist_m < 1000 else f"{dist_m / 1000:.1f}km"
            minutes = max(1, dur_s // 60)
            time = f"{minutes}分钟" if minutes < 60 else f"{minutes // 60}小时{minutes % 60}分钟"
        else:
            distance = "未知"
            time = "未知"

        connections.append({
            "from": from_id,
            "to": to_id,
            "distance": distance,
            "time": time,
            "mode": mode_label,
        })
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
