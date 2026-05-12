import json
from typing import TypedDict
from langchain_core.messages import HumanMessage


class Constraints(TypedDict):
    city: str | None
    area: str | None
    start_location: str | None
    end_location: str | None
    time_slot: str | None
    duration_minutes: int | None
    budget: int | None
    people_count: int | None
    preferences: list[str]
    avoid_tags: list[str]
    transport_mode: str
    queue_tolerance: int
    pace: str
    must_visit: list[str]


DEFAULT_CONSTRAINTS: Constraints = {
    "city": None,
    "area": None,
    "start_location": None,
    "end_location": None,
    "time_slot": None,
    "duration_minutes": None,
    "budget": None,
    "people_count": None,
    "preferences": [],
    "avoid_tags": [],
    "transport_mode": "walking",
    "queue_tolerance": 2,
    "pace": "relaxed",
    "must_visit": [],
}

PARSE_PROMPT = """你是行程规划助手的约束解析模块。从用户消息中提取结构化出行约束。

当前已知约束：
{current_constraints}

用户最新消息：{message}

请严格返回 JSON（不要有其他内容）：
{{
  "city": "城市名",
  "area": "区域/商圈，如西湖、湖滨、武林",
  "time_slot": "时间描述，如周六下午、明天上午",
  "duration_minutes": 预计游玩时长（分钟），半天约240，一天约480,
  "budget": 总预算数字（int）,
  "people_count": 人数（int）,
  "preferences": ["偏好标签列表"],
  "avoid_tags": ["要避免的标签，如排队"],
  "transport_mode": "walking/bicycling/driving/transit",
  "queue_tolerance": 1-3（1=不想排队，2=可接受，3=无所谓）,
  "pace": "relaxed/balanced/intense",
  "must_visit": ["必去地点"]
}}

偏好标签可选值：美食、咖啡、看展、自然、购物、亲子、夜景、探店、拍照、历史

规则：
- 只更新用户这次明确提到的字段，没提到的用 null
- 用户说"不想排队"→ queue_tolerance=1, avoid_tags加入"排队"
- 用户说"轻松"/"少走路"→ pace="relaxed", transport_mode="walking"
- 用户说"紧凑"/"赶时间"→ pace="intense"
- 预算要解析为单人还是总预算，根据上下文判断"""


def parse_constraints(message: str, current: dict, llm) -> Constraints:
    """解析用户消息为结构化约束"""
    current_str = json.dumps(current, ensure_ascii=False, indent=2)
    prompt = PARSE_PROMPT.format(current_constraints=current_str, message=message)

    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content.strip()

    # 清理 markdown 代码块
    if content.startswith("```"):
        content = content.split("\n", 1)[-1]
        content = content.rsplit("```", 1)[0]

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return current

    # 合并结果
    result = {**current}
    for key in DEFAULT_CONSTRAINTS:
        if key in data and data[key] is not None:
            if key == "preferences" and isinstance(data[key], list):
                result[key] = list(set(result.get(key, []) + data[key]))
            elif key == "avoid_tags" and isinstance(data[key], list):
                result[key] = list(set(result.get(key, []) + data[key]))
            else:
                result[key] = data[key]

    return result


def resolve_area(constraints: dict) -> dict:
    """解析区域为中心坐标和搜索半径"""
    city = constraints.get("city", "杭州")
    area = constraints.get("area", "")

    # 区域别名映射
    area_aliases = {
        "西湖": {"center": "120.148792,30.247173", "radius": 4000, "adcode": "330100"},
        "湖滨": {"center": "120.163000,30.250000", "radius": 2000, "adcode": "330100"},
        "武林": {"center": "120.170000,30.270000", "radius": 3000, "adcode": "330100"},
        "钱江新城": {"center": "120.210000,30.250000", "radius": 4000, "adcode": "330100"},
        "西溪": {"center": "120.070000,30.270000", "radius": 5000, "adcode": "330100"},
        "滨江": {"center": "120.210000,30.210000", "radius": 4000, "adcode": "330100"},
    }

    if area and area in area_aliases:
        return area_aliases[area]

    # 默认返回城市中心
    city_centers = {
        "杭州": {"center": "120.155148,30.274162", "radius": 10000, "adcode": "330100"},
        "北京": {"center": "116.397428,39.90923", "radius": 15000, "adcode": "110100"},
        "上海": {"center": "121.473701,31.230416", "radius": 15000, "adcode": "310100"},
    }

    return city_centers.get(city, {"center": "120.155148,30.274162", "radius": 10000, "adcode": "330100"})


def is_info_complete(constraints: Constraints) -> tuple[bool, list[str]]:
    """检查约束信息是否完整"""
    missing = []

    if not constraints.get("city") and not constraints.get("area"):
        missing.append("位置/城市")

    if not constraints.get("time_slot"):
        missing.append("出行时间")

    has_optional = (
        constraints.get("budget")
        or constraints.get("preferences")
        or constraints.get("people_count")
    )

    if not has_optional:
        missing.append("预算或偏好")

    return len(missing) == 0, missing
