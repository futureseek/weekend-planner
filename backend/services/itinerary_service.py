import json
import uuid
from langchain_core.messages import HumanMessage

from services.intent_parser import parse_constraints, resolve_area, is_info_complete, DEFAULT_CONSTRAINTS
from services.poi_service import search_or_fetch_pois
from services.review_service import enrich_reviews
from services.route_optimizer import optimize_route
from db.database import execute_write


EXPLAIN_PROMPT = """你是行程规划助手，需要为用户解释路线方案。

用户需求：{query}

路线方案：
{route_info}

要求：
1. 简短总结这条路线的特点（2-3句话）
2. 说明为什么这样排序
3. 提及用户关心的约束是否被满足（预算、排队、偏好等）
4. 如果某项数据不确定，说明"暂无可靠数据"

不要新增、替换或编造 POI。不要编造营业时间、排队时长、价格。"""


def generate_itinerary(message: str, llm, user_id: str = "default") -> dict:
    """完整路线生成流程"""
    # 1. 约束解析
    constraints = parse_constraints(message, DEFAULT_CONSTRAINTS, llm)
    print(f"[itinerary] 约束解析完成: {json.dumps(constraints, ensure_ascii=False)}")

    # 2. 检查信息完整性
    complete, missing = is_info_complete(constraints)
    if not complete:
        return {
            "status": "need_info",
            "missing": missing,
            "constraints": constraints,
            "reply": _build_ask_message(missing, constraints),
        }

    # 3. 区域解析
    area_info = resolve_area(constraints)
    print(f"[itinerary] 区域解析: {area_info}")

    # 4. POI 候选收集
    city = constraints.get("city", "杭州")
    preferences = constraints.get("preferences", [])
    budget = constraints.get("budget")
    max_cost = budget * 0.4 if budget else None  # 单个 POI 最多占预算 40%

    pois = search_or_fetch_pois(city, preferences, max_cost, limit=10)
    print(f"[itinerary] POI 收集: {len(pois)} 个候选")

    if not pois:
        return {
            "status": "no_poi",
            "constraints": constraints,
            "reply": "抱歉，没有找到符合条件的地点。请尝试调整偏好或预算。",
        }

    # 5. UGC 摘要补全
    pois = enrich_reviews(pois)
    print(f"[itinerary] UGC 补全完成")

    # 6. 路线优化
    opt_result = optimize_route(pois, constraints, max_stops=5,
                                area_center=area_info.get("center"))
    plans = opt_result["plans"]
    matrix = opt_result["matrix"]
    print(f"[itinerary] 路线优化完成: {len(plans)} 个方案")

    if not plans:
        return {
            "status": "optimization_failed",
            "constraints": constraints,
            "reply": "抱歉，无法生成有效的路线方案。请尝试调整条件。",
        }

    # 7. LLM 生成解释
    explanations = []
    for plan in plans:
        route_info = _format_route_for_explain(plan)
        explanation = _generate_explanation(message, route_info, llm)
        explanations.append(explanation)

    # 8. 构建结果
    itinerary_id = f"itn_{uuid.uuid4().hex[:8]}"
    primary_plan = plans[0]

    transport_mode = constraints.get("transport_mode", "walking")
    result = {
        "id": itinerary_id,
        "blocks": _build_blocks(primary_plan["route"]),
        "connections": _build_connections(primary_plan["route"], matrix, transport_mode),
        "total_duration": primary_plan["score"].get("total_duration_s", 0) // 60,
        "total_price": primary_plan["score"].get("total_cost", 0),
        "score": primary_plan["score"].get("route_score", 0),
        "constraints": constraints,
    }

    alternatives = []
    for i, plan in enumerate(plans[1:], 1):
        alt = {
            "name": plan["name"],
            "blocks": _build_blocks(plan["route"]),
            "connections": _build_connections(plan["route"], matrix, transport_mode),
            "total_duration": plan["score"].get("total_duration_s", 0) // 60,
            "total_price": plan["score"].get("total_cost", 0),
            "score": plan["score"].get("route_score", 0),
        }
        alternatives.append(alt)

    # 保存到数据库
    execute_write("""
        INSERT INTO itinerary (id, user_id, query, constraints, result_json, score)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        itinerary_id,
        user_id,
        message,
        json.dumps(constraints, ensure_ascii=False),
        json.dumps(result, ensure_ascii=False),
        result["score"],
    ))

    reply = explanations[0] if explanations else "已为你规划好路线！"

    return {
        "status": "success",
        "itinerary": result,
        "alternatives": alternatives,
        "explanations": explanations,
        "constraints": constraints,
        "reply": reply,
    }


def adjust_itinerary(itinerary_id: str, action: str, llm, user_id: str = "default") -> dict:
    """动态调整路线"""
    from db.database import execute_one
    itinerary = execute_one("SELECT * FROM itinerary WHERE id = ?", (itinerary_id,))

    if not itinerary:
        return {"status": "not_found", "reply": "未找到该行程方案。"}

    result = json.loads(itinerary["result_json"])
    constraints = json.loads(itinerary["constraints"])

    # 根据动作调整约束
    if action == "less_walking":
        constraints["pace"] = "relaxed"
        constraints["transport_mode"] = "bicycling"
    elif action == "less_queue":
        constraints["queue_tolerance"] = 1
    elif action == "lower_budget":
        constraints["budget"] = int(constraints.get("budget", 300) * 0.7)
    elif action == "replace_poi":
        # TODO: 实现替换特定 POI
        pass

    # 重新生成
    query = itinerary["query"]
    return generate_itinerary(query, llm, user_id)


def _build_ask_message(missing: list[str], constraints: dict) -> str:
    """构建追问消息"""
    parts = []
    if "位置/城市" in missing:
        parts.append("你想去哪个城市或区域玩？")
    if "出行时间" in missing:
        parts.append("计划什么时候出发？")
    if "预算或偏好" in missing:
        parts.append("大概预算多少？或者有什么偏好，比如美食、看展、咖啡？")

    return " ".join(parts) if parts else "请告诉我更多出行需求。"


def _format_route_for_explain(plan: dict) -> str:
    """格式化路线信息供 LLM 解释"""
    lines = [f"方案名称：{plan['name']}"]
    lines.append(f"总分：{plan['score'].get('route_score', 0)}")
    lines.append(f"总距离：{plan['score'].get('total_distance_m', 0)}米")
    lines.append(f"总时间：{plan['score'].get('total_duration_s', 0) // 60}分钟")
    lines.append(f"总花费：¥{plan['score'].get('total_cost', 0)}")
    lines.append("\n路线顺序：")

    for i, poi in enumerate(plan["route"], 1):
        cost = poi.get("avg_cost", 0)
        cost_str = f"¥{cost}" if cost > 0 else "免费"
        lines.append(f"{i}. {poi['name']} ({poi['category']}, 人均{cost_str})")

    return "\n".join(lines)


def _generate_explanation(query: str, route_info: str, llm) -> str:
    """生成路线解释"""
    prompt = EXPLAIN_PROMPT.format(query=query, route_info=route_info)
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content


def _build_blocks(route: list[dict]) -> list[dict]:
    """构建行程卡片数据"""
    blocks = []
    for i, poi in enumerate(route):
        block = {
            "id": poi["id"],
            "name": poi["name"],
            "category": poi.get("category", ""),
            "icon": _get_category_icon(poi.get("category", "")),
            "duration": 60,
            "price": poi.get("avg_cost", 0),
            "rating": poi.get("rating", 0),
            "address": poi.get("address", ""),
            "reason": _build_recommend_reason(poi),
            "tags": json.loads(poi.get("tags", "[]")) if isinstance(poi.get("tags"), str) else poi.get("tags", []),
        }
        blocks.append(block)
    return blocks


def _build_connections(route: list[dict], matrix: dict = None, mode: str = "walking") -> list[dict]:
    """构建路线连接数据，使用真实路线矩阵"""
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


def _build_recommend_reason(poi: dict) -> str:
    """构建推荐理由"""
    parts = []
    rating = poi.get("rating", 0)
    if rating and rating >= 4.5:
        parts.append(f"评分{rating}，口碑很好")

    review = poi.get("review", {})
    keywords = review.get("keywords", [])
    if "推荐" in keywords or "必去" in keywords:
        parts.append("用户推荐")
    if "出片" in keywords or "拍照" in keywords:
        parts.append("适合拍照")
    if "环境好" in keywords:
        parts.append("环境好")

    avg_cost = poi.get("avg_cost", 0)
    if avg_cost == 0:
        parts.append("免费")

    return "，".join(parts) if parts else "值得一去"
