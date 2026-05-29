import json
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .state import PlannerState
from .context import build_context


def _log(node: str, msg: str):
    print(f"[{node}] {msg}")


INTENT_PROMPT = """你是行程规划助手的意图识别模块。从用户消息中提取结构化信息。

当前已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

用户最新消息：{message}

请严格返回 JSON（不要有其他内容）：
{{
  "intent": "plan" 或 "modify" 或 "chat",
  "location": "位置，没提到则保持原值",
  "budget": 预算数字（int），没提到则保持原值,
  "preferences": ["偏好列表"],没提到则保持原值,
  "people_count": 人数（int），没提到则保持原值,
  "time_slot": "时间段"，没提到则保持原值,
  "force_generate": true 或 false,
  "modify_action": null 或 "less_walking" 或 "less_queue" 或 "lower_budget" 或 "replace_poi",
  "modify_payload": null 或 {{"category": "餐厅"}}
}}

规则：
- intent=plan：用户在描述出行需求
- intent=modify：用户想修改已有行程（如"换个餐厅"、"去掉这个地方"、"少走点路"）
- intent=chat：闲聊（天气、笑话等与行程无关的）
- 用户说"就这样"/"随便"/"不用问了"/"直接生成"时 force_generate=true
- 只更新用户这次明确提到的字段，没提到的保持原值（用null表示未提到）
- modify_action 提取用户想做的修改类型：
  - "换个餐厅"/"换吃的" → replace_poi + payload.category="餐厅"
  - "换个咖啡" → replace_poi + payload.category="咖啡"
  - "少走点路" → less_walking
  - "不想排队" → less_queue
  - "省钱一点" → lower_budget
  - 无法识别具体修改 → modify_action=null"""

ASK_PROMPT = """你是行程规划助手，现在需要向用户确认一些信息。

已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

缺失的关键信息：{missing}

请用自然友好的方式，一次性询问缺失信息（最多问2个问题）。
要求：口语化、简短、有emoji。不要重复已知信息。"""

CHAT_PROMPT = """你是"周末去哪儿"AI行程规划助手。
用户在和你闲聊，请简短友好地回复，并自然地引导用户描述出行需求。
保持在2-3句话以内。"""


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def intent_node(state: PlannerState, llm) -> dict:
    _log("intent", f"进入意图识别, 消息数={len(state.get('messages', []))}")
    context = build_context(state)
    prompt = INTENT_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "未知",
        preferences=state.get("preferences") or "未知",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "未知",
        message=state["messages"][-1].content,
    )

    response = llm.invoke(context + [HumanMessage(content=prompt)])
    data = _parse_json(response.content)

    if not data:
        _log("intent", "JSON解析失败，默认intent=plan")
        return {"intent": "plan"}

    result = {
        "intent": data.get("intent", "plan"),
        "force_generate": data.get("force_generate", False),
    }

    # 提取修改动作
    if result["intent"] == "modify":
        modify_action = data.get("modify_action")
        modify_payload = data.get("modify_payload")
        if modify_action:
            result["modify_action"] = modify_action
            result["modify_payload"] = modify_payload
            # modify 走数据管线，需要 force_generate
            result["force_generate"] = True

    for field in ["location", "budget", "preferences", "people_count", "time_slot"]:
        val = data.get(field)
        if val is not None and val != "null":
            result[field] = val

    _log("intent", f"结果: intent={result['intent']}, location={result.get('location')}, budget={result.get('budget')}, force={result.get('force_generate')}")
    return result


def check_node(state: PlannerState) -> dict:
    required = ["location", "time_slot"]
    has_required = all(state.get(f) for f in required)
    has_optional = bool(state.get("budget") or state.get("preferences"))
    info_complete = has_required and has_optional

    _log("check", f"完整性检查: location={state.get('location')}, time={state.get('time_slot')}, budget={state.get('budget')}, prefs={state.get('preferences')} → complete={info_complete}, ask_count={state.get('ask_count', 0)}")

    return {
        "info_complete": info_complete,
        "turn_number": state.get("turn_number", 0) + 1,
    }


def ask_node(state: PlannerState, llm) -> dict:
    missing = []
    if not state.get("location"):
        missing.append("位置/城市")
    if not state.get("budget"):
        missing.append("预算")
    if not state.get("preferences"):
        missing.append("偏好（如探店、看展、美食等）")
    if not state.get("time_slot"):
        missing.append("出行时间")

    context = build_context(state)
    prompt = ASK_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "未知",
        preferences=state.get("preferences") or "未知",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "未知",
        missing="、".join(missing),
    )

    response = llm.invoke(context + [HumanMessage(content=prompt)])
    _log("ask", f"追问完成, ask_count={state.get('ask_count', 0) + 1}")

    return {
        "messages": [AIMessage(content=response.content)],
        "ask_count": state.get("ask_count", 0) + 1,
    }


def chat_node(state: PlannerState, llm) -> dict:
    context = build_context(state)
    response = llm.invoke(context + [HumanMessage(content=CHAT_PROMPT)])

    return {
        "messages": [AIMessage(content=response.content)],
    }


# ============ 新增节点：数据驱动流程 ============

def collect_data_node(state: PlannerState, llm) -> dict:
    """数据收集节点：解析约束、查询 POI、补全评价，支持修改逻辑"""
    _log("collect_data", "进入数据收集节点")

    from services.intent_parser import parse_constraints, resolve_area, DEFAULT_CONSTRAINTS
    from services.poi_service import search_or_fetch_pois
    from services.review_service import enrich_reviews

    # 解析约束：如果有已有约束（修改场景），以此为基础；否则从头解析
    existing_constraints = state.get("constraints")
    if existing_constraints:
        current_constraints = existing_constraints
    else:
        current_constraints = {
            "city": state.get("location", "").replace("市", "").replace("区", ""),
            "area": state.get("location", ""),
            "time_slot": state.get("time_slot"),
            "budget": state.get("budget"),
            "people_count": state.get("people_count"),
            "preferences": state.get("preferences", []),
            "avoid_tags": [],
            "transport_mode": "walking",
            "queue_tolerance": 1 if "不想排队" in str(state.get("messages", "")) else 2,
            "pace": "relaxed",
            "must_visit": [],
        }

    # 解析约束（修改场景下仍解析以获取用户新提到的信息）
    last_message = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    constraints = parse_constraints(last_message, current_constraints, llm)

    # 处理修改逻辑：如果有 modify_action，合并到约束中
    modify_action = state.get("modify_action")
    modify_payload = state.get("modify_payload") or {}
    if modify_action:
        if modify_action == "replace_poi":
            constraints["must_replace_type"] = modify_payload.get("category", "餐厅")
        elif modify_action == "less_walking":
            constraints["distance_weight_boost"] = 3.0
        elif modify_action == "less_queue":
            constraints["queue_tolerance"] = 1
        elif modify_action == "lower_budget":
            constraints["budget"] = int(constraints.get("budget", 300) * 0.7)
        _log("collect_data", f"修改动作: {modify_action}")

    _log("collect_data", f"约束: {json.dumps(constraints, ensure_ascii=False)}")

    # 区域解析
    area_info = resolve_area(constraints)
    _log("collect_data", f"区域: {area_info}")

    # 搜索 POI
    city = constraints.get("city", "杭州")
    preferences = constraints.get("preferences", [])
    budget = constraints.get("budget")
    max_cost = budget * 0.4 if budget else None

    pois = search_or_fetch_pois(city, preferences, max_cost, limit=10)

    # 如果是替换 POI 操作，排除当前行程中同类型的 POI
    if modify_action == "replace_poi" and state.get("itinerary"):
        replace_type = constraints.get("must_replace_type", "餐厅")
        current_ids = {b["id"] for b in state["itinerary"].get("blocks", [])
                       if b.get("category") == replace_type}
        pois = [p for p in pois if p["id"] not in current_ids]
        _log("collect_data", f"排除 {len(current_ids)} 个同类 POI")

    _log("collect_data", f"找到 {len(pois)} 个 POI")

    # 补全评价
    pois = enrich_reviews(pois)
    _log("collect_data", "评价补全完成")

    return {
        "constraints": constraints,
        "candidate_pois": pois,
        "area_info": area_info,
        "modify_action": None,
        "modify_payload": None,
    }


def rank_poi_node(state: PlannerState) -> dict:
    """POI 打分节点"""
    _log("rank_poi", "进入打分节点")

    from services.route_optimizer import score_poi

    pois = state.get("candidate_pois", [])
    constraints = state.get("constraints", {})

    for poi in pois:
        poi["_score"] = score_poi(poi, constraints)

    # 按分数排序
    pois.sort(key=lambda x: x.get("_score", 0), reverse=True)

    _log("rank_poi", f"打分完成，Top3: {[p['name'] for p in pois[:3]]}")

    return {"candidate_pois": pois}


def optimize_route_node(state: PlannerState) -> dict:
    """路线优化节点"""
    _log("optimize", "进入路线优化节点")

    from services.route_optimizer import optimize_route

    pois = state.get("candidate_pois", [])
    constraints = state.get("constraints", {})
    area_info = state.get("area_info") or {}
    area_center = area_info.get("center")
    transport_mode = constraints.get("transport_mode", "walking")

    # 少走路时减少站点数，直接缩短总距离
    dist_boost = constraints.get("distance_weight_boost", 1.0)
    max_stops = 4 if dist_boost > 1.5 else 5

    opt_result = optimize_route(pois, constraints, max_stops=max_stops, area_center=area_center)
    plans = opt_result["plans"]
    matrix = opt_result["matrix"]
    _log("optimize", f"生成 {len(plans)} 个方案")

    if not plans:
        return {"itinerary": None, "alternative_plans": []}

    # 主方案
    primary = plans[0]
    itinerary = {
        "blocks": _build_blocks(primary["route"]),
        "connections": _build_connections(primary["route"], matrix, transport_mode),
        "total_duration": primary["score"].get("total_duration_s", 0) // 60,
        "total_price": primary["score"].get("total_cost", 0),
        "score": primary["score"].get("route_score", 0),
        "plan_name": primary["name"],
    }

    # 备选方案
    alternatives = []
    for plan in plans[1:]:
        alt = {
            "name": plan["name"],
            "blocks": _build_blocks(plan["route"]),
            "connections": _build_connections(plan["route"], matrix, transport_mode),
            "total_duration": plan["score"].get("total_duration_s", 0) // 60,
            "total_price": plan["score"].get("total_cost", 0),
        }
        alternatives.append(alt)

    return {
        "itinerary": itinerary,
        "alternative_plans": alternatives,
    }


def explain_node(state: PlannerState, llm) -> dict:
    """解释节点：LLM 生成自然语言说明"""
    _log("explain", "进入解释节点")

    itinerary = state.get("itinerary")
    if not itinerary:
        return {"messages": [AIMessage(content="抱歉，无法生成有效路线。")]}

    # 构建解释提示
    blocks = itinerary.get("blocks", [])
    route_desc = []
    for i, block in enumerate(blocks, 1):
        cost = block.get("price", 0)
        cost_str = f"¥{cost}" if cost > 0 else "免费"
        route_desc.append(f"{i}. {block['name']} ({block.get('category', '')}, 人均{cost_str})")

    route_text = "\n".join(route_desc)
    constraints = state.get("constraints", {})

    prompt = f"""你是行程规划助手，为用户解释路线方案。

用户偏好：{constraints.get('preferences', [])}
预算：{constraints.get('budget', '未知')}
时间：{constraints.get('time_slot', '未知')}

规划路线：
{route_text}

总时间：{itinerary.get('total_duration', 0)}分钟
总花费：¥{itinerary.get('total_price', 0)}

请用简洁友好的方式介绍这条路线，说明：
1. 路线特点（2-3句话）
2. 为什么这样安排
3. 用户关心的约束是否满足

保持口语化，不要编造信息。"""

    response = llm.invoke([HumanMessage(content=prompt)])
    _log("explain", "解释生成完成")

    return {
        "messages": [AIMessage(content=response.content)],
    }


def _build_blocks(route: list[dict]) -> list[dict]:
    """构建行程卡片数据"""
    import json as _json
    blocks = []
    for poi in route:
        category = poi.get("category", "")
        block = {
            "id": poi["id"],
            "name": poi["name"],
            "category": category,
            "type": _get_frontend_type(category),
            "icon": _get_category_icon(category),
            "duration": 60,
            "price": poi.get("avg_cost", 0),
            "rating": poi.get("rating", 0),
            "address": poi.get("address", ""),
            "tags": _json.loads(poi.get("tags", "[]")) if isinstance(poi.get("tags"), str) else poi.get("tags", []),
        }
        blocks.append(block)
    return blocks


def _get_frontend_type(category: str) -> str:
    """将中文类别映射为前端 TYPE_COLORS 的英文 key"""
    mapping = {
        "咖啡": "cafe",
        "餐厅": "food",
        "景点": "scenic",
        "展览": "exhibition",
        "公园": "park",
        "购物": "shopping",
        "甜品": "food",
        "夜景": "entertainment",
    }
    return mapping.get(category, "scenic")


def _build_connections(route: list[dict], matrix: dict = None, mode: str = "walking") -> list[dict]:
    """构建路线连接，使用真实路线矩阵"""
    mode_label = {"walking": "步行", "bicycling": "骑行", "driving": "驾车"}.get(mode, "步行")
    connections = []
    for i in range(len(route) - 1):
        from_id = route[i]["id"]
        to_id = route[i + 1]["id"]
        key = (from_id, to_id)

        if matrix and key in matrix:
            dist_m = matrix[key]["distance_m"]
            dur_s = matrix[key]["duration_s"]
            distance = f"{dist_m}m" if dist_m < 1000 else f"{dist_m / 1000:.1f}km"
            minutes = dur_s // 60
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
    """获取类别图标"""
    icons = {
        "咖啡": "coffee",
        "餐厅": "food",
        "景点": "scenic",
        "展览": "art",
        "公园": "park",
        "购物": "shop",
        "甜品": "dessert",
    }
    return icons.get(category, "location")
