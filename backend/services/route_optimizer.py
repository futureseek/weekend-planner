import json
import math
import re
from itertools import permutations
from db.database import execute_one, execute_write

FOOD_CATEGORIES = {"餐厅", "咖啡", "甜品"}
ACTIVITY_CATEGORIES = {"景点", "展览", "公园", "购物", "娱乐", "夜景"}

CATEGORY_DEFAULT_COST = {
    "咖啡": 40,
    "餐厅": 150,
    "甜品": 35,
    "购物": 260,
    "夜景": 120,
    "景点": 50,
    "展览": 80,
    "公园": 0,
    "娱乐": 220,
}

NAME_COST_RULES = [
    (("长隆", "乐园", "动物世界", "水上乐园", "欢乐世界"), 260),
    (("广州塔", "观景台", "摩天轮"), 180),
    (("演唱会", "音乐节", "Livehouse", "livehouse", "剧场", "演出"), 180),
    (("密室", "剧本杀", "电竞", "电玩", "桌游"), 150),
    (("太古汇", "万象城", "K11", "天河城", "购物中心", "商场", "步行街"), 180),
    (("酒家", "粤菜", "火锅", "烧肉", "牛排", "私房菜", "茶楼"), 150),
]

QUALITY_FOOD_KEYWORDS = ("酒家", "食府", "茶楼", "粤菜", "海鲜", "老字号", "饭店", "私房菜", "茶点", "茶餐厅")
LIGHT_FOOD_KEYWORDS = (
    "冰室", "糖水", "肠粉", "小食", "米糕", "粉", "面", "瑞幸", "蜜雪", "甜品",
    "肯德基", "KFC", "麦当劳", "汉堡王", "萨莉亚", "Saizeriya", "必胜客",
)

PREFERENCE_CATEGORY_BONUS = {
    "美食": {"餐厅": 0.18, "甜品": 0.06},
    "咖啡": {"咖啡": 0.18, "甜品": 0.04},
    "探店": {"咖啡": 0.12, "甜品": 0.08, "购物": 0.06},
    "看展": {"展览": 0.20, "景点": 0.06},
    "自然": {"公园": 0.16, "景点": 0.12},
    "爬山": {"公园": 0.18, "景点": 0.16},
    "户外": {"公园": 0.18, "景点": 0.12, "娱乐": 0.04},
    "运动": {"娱乐": 0.16, "公园": 0.08},
    "游戏": {"娱乐": 0.22, "购物": 0.06},
    "娱乐": {"娱乐": 0.18, "夜景": 0.08, "购物": 0.04},
    "购物": {"购物": 0.20, "餐厅": 0.04},
    "亲子": {"公园": 0.14, "展览": 0.14, "景点": 0.08},
    "夜景": {"夜景": 0.22, "娱乐": 0.08},
    "拍照": {"景点": 0.14, "展览": 0.10, "咖啡": 0.05},
    "历史": {"展览": 0.16, "景点": 0.14},
    "热闹": {"购物": 0.12, "夜景": 0.12, "娱乐": 0.08},
    "休闲": {"咖啡": 0.12, "公园": 0.10, "甜品": 0.08, "娱乐": 0.06},
}

PREFERENCE_STYLE_RECIPES = {
    "游戏": [("娱乐", 2), ("餐厅", 1), ("购物", 1), ("夜景", 1), ("咖啡", 1), ("甜品", 1)],
    "爬山": [("公园", 2), ("景点", 2), ("餐厅", 1), ("咖啡", 1), ("夜景", 1)],
    "户外": [("公园", 2), ("景点", 2), ("餐厅", 1), ("咖啡", 1), ("夜景", 1)],
    "购物": [("购物", 2), ("餐厅", 1), ("咖啡", 1), ("甜品", 1), ("夜景", 1)],
    "看展": [("展览", 2), ("咖啡", 1), ("餐厅", 1), ("景点", 1), ("夜景", 1)],
    "历史": [("展览", 2), ("景点", 2), ("餐厅", 1), ("咖啡", 1)],
    "亲子": [("公园", 2), ("展览", 1), ("景点", 1), ("餐厅", 1), ("甜品", 1)],
    "夜景": [("景点", 1), ("餐厅", 1), ("娱乐", 1), ("夜景", 2), ("咖啡", 1)],
    "休闲": [("餐厅", 1), ("咖啡", 1), ("公园", 1), ("甜品", 1), ("娱乐", 1), ("夜景", 1)],
}


def haversine_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """计算两点直线距离，单位米。"""
    r = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _safe_tags(poi: dict) -> list[str]:
    tags = poi.get("tags", [])
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return [tags]
    return tags if isinstance(tags, list) else []


def _poi_text(poi: dict) -> str:
    return " ".join([
        str(poi.get("name") or ""),
        str(poi.get("category") or ""),
        str(poi.get("type") or ""),
        str(poi.get("address") or ""),
        *map(str, _safe_tags(poi)),
    ])


def _is_unavailable_poi(poi: dict) -> bool:
    text = _poi_text(poi)
    return any(
        keyword in text
        for keyword in ["不对外开放", "暂不开放", "暂停开放", "未开放", "内部使用", "内部区域", "非开放区域", "谢绝参观"]
    )


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _budget_limit(constraints: dict | None) -> float | None:
    budget = _to_float((constraints or {}).get("budget"), 0)
    return budget if budget > 0 else None


def _route_total_cost(route: list[dict], constraints: dict) -> float:
    people_count = max(1, int((constraints or {}).get("people_count") or 1))
    return sum(_effective_unit_cost(poi) * people_count for poi in route)


def _within_budget(route: list[dict], constraints: dict) -> bool:
    budget_limit = _budget_limit(constraints)
    return budget_limit is None or _route_total_cost(route, constraints) <= budget_limit


def _effective_unit_cost(poi: dict) -> float:
    cost = _to_float(poi.get("avg_cost"), 0)
    if cost > 0:
        return cost
    category = poi.get("category", "")
    tags = _safe_tags(poi)
    if "免费" in tags:
        return 0
    text = " ".join([str(poi.get("name") or ""), str(poi.get("address") or ""), *map(str, tags)])
    for keywords, default_cost in NAME_COST_RULES:
        if any(keyword in text for keyword in keywords):
            return default_cost
    return CATEGORY_DEFAULT_COST.get(category, 30)


def _food_quality_signal(poi: dict) -> float:
    if poi.get("category") not in {"餐厅", "甜品", "咖啡"}:
        return 0.0
    text = " ".join([str(poi.get("name") or ""), str(poi.get("address") or ""), *map(str, _safe_tags(poi))])
    score = 0.0
    if any(keyword in text for keyword in QUALITY_FOOD_KEYWORDS):
        score += 1.0
    if any(keyword in text for keyword in LIGHT_FOOD_KEYWORDS):
        score -= 0.6
    avg_cost = _to_float(poi.get("avg_cost"), 0)
    if poi.get("category") == "餐厅" and avg_cost >= 80:
        score += 0.5
    return score


def _premium_sort_key(poi: dict) -> tuple[float, float, float]:
    return (_food_quality_signal(poi), _effective_unit_cost(poi), poi.get("_score", 0))


def _preference_match_score(poi: dict, preferences: list[str]) -> float:
    if not preferences:
        return 0.55

    tags = _safe_tags(poi)
    category = poi.get("category", "")
    text = " ".join([category, poi.get("name", ""), *tags])
    matched = 0

    expanded = {
        "美食": ["餐厅", "甜品", "小吃", "本地菜", "吃饭"],
        "咖啡": ["咖啡", "下午茶", "探店"],
        "看展": ["展览", "美术馆", "博物馆", "艺术"],
        "自然": ["公园", "景点", "自然", "湖", "山", "湿地"],
        "爬山": ["山", "登山", "徒步", "步道", "森林", "公园", "景点"],
        "户外": ["户外", "露营", "骑行", "徒步", "森林", "公园", "景点"],
        "运动": ["运动", "攀岩", "骑行", "篮球", "娱乐", "公园"],
        "游戏": ["游戏", "电竞", "电玩", "桌游", "密室", "剧本杀", "娱乐", "网咖"],
        "娱乐": ["演出", "市集", "剧场", "livehouse", "娱乐", "夜景"],
        "购物": ["购物", "商场", "商圈", "逛街"],
        "亲子": ["亲子", "公园", "博物馆", "轻松"],
        "夜景": ["夜景", "酒吧", "晚上", "地标"],
        "探店": ["咖啡", "甜品", "文艺", "网红", "小店"],
        "拍照": ["拍照", "打卡", "出片", "景观"],
        "历史": ["历史", "文化", "老街", "博物馆"],
        "热闹": ["商场", "商圈", "夜景", "热门", "人气", "购物"],
        "少排队": ["安静", "平价", "稳定"],
    }

    for pref in preferences:
        keywords = expanded.get(pref, [pref])
        if any(keyword in text for keyword in keywords):
            matched += 1

    return min(matched / max(len(preferences), 1), 1.0)


def score_poi(poi: dict, constraints: dict, user_profile: dict = None, area_center: tuple = None) -> float:
    """对单个 POI 打分，综合偏好、评分、预算、距离和排队风险。"""
    preferences = constraints.get("preferences", []) or []
    score = 0.0
    area_center = _parse_center(area_center)
    tags = _safe_tags(poi)
    poi_text = " ".join([str(poi.get("name") or ""), str(poi.get("category") or ""), str(poi.get("address") or ""), *map(str, tags)])

    preference_match = _preference_match_score(poi, preferences)
    score += 0.38 * preference_match
    category = poi.get("category", "")
    for pref in preferences:
        score += PREFERENCE_CATEGORY_BONUS.get(pref, {}).get(category, 0)

    rating = _to_float(poi.get("rating"), 4.0)
    score += 0.16 * min(rating / 5.0, 1.0)

    people_count = max(1, int(constraints.get("people_count") or 1))
    budget = constraints.get("budget")
    per_person_budget = (budget / people_count) if budget else None
    avg_cost = _effective_unit_cost(poi)
    if per_person_budget and avg_cost:
        if avg_cost <= per_person_budget * 0.25:
            cost_fit = 0.90
        elif avg_cost <= per_person_budget * 0.55:
            cost_fit = 1.0
        elif avg_cost <= per_person_budget:
            cost_fit = 0.78
        else:
            cost_fit = 0.25
    else:
        cost_fit = 0.65
    score += 0.13 * cost_fit

    if constraints.get("budget_level") in {"comfort", "premium"} and category in {"餐厅", "甜品", "咖啡"}:
        food_quality = _food_quality_signal(poi)
        score += 0.08 * food_quality
        if category == "餐厅" and avg_cost and avg_cost < 50 and food_quality < 0:
            score -= 0.08
    if constraints.get("food_priority") == "quality" and category in {"餐厅", "甜品", "咖啡"}:
        food_quality = _food_quality_signal(poi)
        score += 0.18 * food_quality
        if category == "餐厅" and any(keyword in poi_text for keyword in LIGHT_FOOD_KEYWORDS):
            score -= 0.34
        if category == "餐厅" and any(keyword in poi_text for keyword in QUALITY_FOOD_KEYWORDS):
            score += 0.12
        if category == "餐厅" and avg_cost and per_person_budget:
            quality_floor = min(max(per_person_budget * 0.18, 70), 160)
            if avg_cost >= quality_floor and avg_cost <= per_person_budget * 0.75:
                score += 0.08

    if area_center and poi.get("lng") and poi.get("lat"):
        dist = haversine_distance(float(poi["lng"]), float(poi["lat"]), area_center[0], area_center[1])
        boost = constraints.get("distance_weight_boost", 1.0)
        decay = max(650, 2600 / boost)
        distance_fit = math.exp(-dist / decay)
    else:
        distance_fit = 0.55
    score += 0.12 * distance_fit

    review = poi.get("review", {}) or {}
    sentiment = _to_float(review.get("sentiment"), 0)
    keywords = review.get("keywords", []) if isinstance(review.get("keywords", []), list) else []
    hot_score = 0.55 + max(sentiment, 0) * 0.3
    if any(kw in ["推荐", "必去", "打卡", "本地人推荐"] for kw in keywords + tags):
        hot_score += 0.12
    guide_positive = constraints.get("guide_positive_keywords") or []
    guide_avoid = constraints.get("guide_avoid_keywords") or []
    guide_hot_places = constraints.get("guide_hot_places") or []
    review_text = str(review.get("content", "") or "")
    if any(
        place and (
            str(place) in poi_text
            or str(poi.get("name") or "") in str(place)
        )
        for place in guide_hot_places[:16]
    ):
        hot_score += 0.24
    if any(keyword in poi_text or keyword in review_text for keyword in guide_positive):
        hot_score += 0.18
    if any(keyword in poi_text or keyword in review.get("content", "") for keyword in guide_avoid):
        hot_score -= 0.18
    score += 0.10 * min(hot_score, 1.0)

    queue_tolerance = constraints.get("queue_tolerance", 2)
    queue_hint = review.get("queue_hint", "unknown")
    if "排队" in tags or queue_hint == "high":
        queue_fit = 0.35 if queue_tolerance <= 1 else 0.65
    elif queue_hint == "medium":
        queue_fit = 0.55 if queue_tolerance <= 1 else 0.75
    else:
        queue_fit = 0.90
    score += 0.10 * queue_fit

    # 给免费或低价公共空间一点基础分，避免路线全是消费点。
    if _to_float(poi.get("avg_cost"), 0) == 0 and poi.get("category") in {"公园", "展览", "景点"}:
        score += 0.03

    return round(score, 4)


def build_route_matrix(pois: list[dict], mode: str = "walking") -> dict:
    """构建 POI 间距离矩阵。当前版本优先用缓存，没有缓存时用直线距离估算。"""
    matrix = {}
    valid_pois = [p for p in pois if p.get("id") and p.get("lng") is not None and p.get("lat") is not None]

    for i, poi_a in enumerate(valid_pois):
        for j, poi_b in enumerate(valid_pois):
            if i >= j:
                continue

            key = (poi_a["id"], poi_b["id"])
            cached = execute_one(
                "SELECT distance_m, duration_s FROM route_cache WHERE origin_poi_id = ? AND dest_poi_id = ? AND mode = ?",
                (poi_a["id"], poi_b["id"], mode),
            )

            if cached:
                dist_m = cached["distance_m"]
                dur_s = cached["duration_s"]
            else:
                dist_m = int(
                    haversine_distance(
                        float(poi_a["lng"]),
                        float(poi_a["lat"]),
                        float(poi_b["lng"]),
                        float(poi_b["lat"]),
                    )
                )
                speed_map = {
                    "walking": 1.2,
                    "bicycling": 4.0,
                    "driving": 10.0,
                    "transit": 7.0,
                }
                speed = speed_map.get(mode, 1.2)
                dur_s = max(60, int(dist_m / speed))
                execute_write(
                    """
                    INSERT OR REPLACE INTO route_cache (origin_poi_id, dest_poi_id, mode, distance_m, duration_s)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (poi_a["id"], poi_b["id"], mode, dist_m, dur_s),
                )

            matrix[key] = {"distance_m": dist_m, "duration_s": dur_s}
            matrix[(poi_b["id"], poi_a["id"])] = {"distance_m": dist_m, "duration_s": dur_s}

    return matrix


def _visit_duration_s(poi: dict) -> int:
    text = _poi_text(poi)
    category = poi.get("category", "")
    if any(keyword in text for keyword in ["商圈", "步行街", "商业街", "购物中心", "太古汇", "万象城", "K11", "天河城", "正佳", "北京路", "上下九", "市桥"]):
        return 120 * 60
    if any(keyword in text for keyword in ["广场", "古镇", "老街", "景区"]):
        return 95 * 60
    if category == "购物":
        return 105 * 60
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
    }.get(poi.get("category", ""), 45) * 60


def calculate_route_score(route: list[dict], matrix: dict, constraints: dict) -> dict:
    total_poi_score = 0.0
    total_distance = 0
    total_duration = 0
    total_cost = 0
    transfer_penalty = 0.0
    people_count = max(1, int(constraints.get("people_count") or 1))

    categories = set()
    for i, poi in enumerate(route):
        total_poi_score += poi.get("_score", 0)
        total_cost += int(_effective_unit_cost(poi) * people_count)
        total_duration += _visit_duration_s(poi)
        categories.add(poi.get("category", ""))

        if i > 0:
            key = (route[i - 1]["id"], poi["id"])
            if key in matrix:
                leg_distance = matrix[key]["distance_m"]
                leg_duration = matrix[key]["duration_s"]
                total_distance += leg_distance
                total_duration += leg_duration
                leg_minutes = leg_duration / 60
                if leg_minutes > 20:
                    transfer_penalty += (leg_minutes - 20) * 0.035
                if leg_distance > 1600:
                    transfer_penalty += ((leg_distance - 1600) / 1000) * 0.28
                if leg_distance > 5000:
                    transfer_penalty += ((leg_distance - 5000) / 1000) * 0.45

    dist_boost = constraints.get("distance_weight_boost", 1.0)
    diversity_bonus = min(len(categories), 5) * 0.12
    desired_categories = _desired_categories(constraints.get("preferences", []) or [])
    preference_coverage = len(categories & desired_categories)
    preference_bonus = preference_coverage * 0.22
    route_score = (
        total_poi_score
        + diversity_bonus
        + preference_bonus
        - 0.00000035 * (total_distance ** 2) * dist_boost
        - 0.007 * (total_duration / 60)
        - transfer_penalty * dist_boost
    )

    budget = constraints.get("budget")
    budget_limit = _budget_limit(constraints)
    if budget:
        if budget_limit and total_cost > budget_limit:
            route_score -= 20 + (total_cost - budget_limit) * 0.2
        else:
            utilization = total_cost / budget
            target_ratio = float(constraints.get("budget_target_ratio") or 0.78)
            # 不鼓励“花得越少越好”的伪最优；预算越充足，越应该升级餐饮、体验或夜间活动。
            route_score += max(0, 0.55 - abs(utilization - target_ratio)) * 2.4
            if utilization < target_ratio - 0.25:
                route_score -= (target_ratio - utilization) * 2.2

    return {
        "route_score": round(route_score, 2),
        "total_poi_score": round(total_poi_score, 2),
        "total_distance_m": total_distance,
        "total_duration_s": total_duration,
        "total_cost": int(total_cost),
        "category_count": len(categories),
    }


def optimize_route(
    pois: list[dict],
    constraints: dict,
    max_stops: int = 5,
    area_center: tuple = None,
) -> dict:
    """生成多风格路线：综合、少走路、吃好玩好、省钱轻量。"""
    if not pois:
        return {"plans": [], "matrix": {}}

    pois = [poi for poi in pois if not _is_unavailable_poi(poi)]
    if not pois:
        return {"plans": [], "matrix": {}}

    center = _parse_center(area_center)
    pois = _filter_by_trip_radius(pois, constraints, center)
    for poi in pois:
        poi["_score"] = score_poi(poi, constraints, area_center=center)

    trip_days = max(1, int(constraints.get("trip_days") or 1))
    if trip_days > 1:
        return _optimize_multiday_route(pois, constraints, trip_days, area_center=center)

    duration_limit = constraints.get("duration_minutes")
    if duration_limit and duration_limit <= 360:
        hard_limit = 12
    elif max_stops <= 6:
        hard_limit = 14
    else:
        hard_limit = 14
    if constraints.get("_fast_adjust"):
        hard_limit = min(hard_limit, max(max_stops + 3, 9))
    candidates = _bucket_and_select(pois, max_stops=max_stops, hard_limit=hard_limit, constraints=constraints)
    matrix = build_route_matrix(candidates, constraints.get("transport_mode", "walking"))
    route_len = min(len(candidates), max_stops)
    if duration_limit:
        route_len = min(route_len, max(4, duration_limit // 75))
    if route_len == 0:
        return {"plans": [], "matrix": matrix}

    all_routes = []
    exact_limit = route_len if constraints.get("_fast_adjust") else (8 if route_len >= 5 else 9)
    search_candidates = candidates[: min(len(candidates), max(route_len, exact_limit))]
    for perm in permutations(search_candidates, route_len):
        route = list(perm)
        score_info = calculate_route_score(route, matrix, constraints)
        all_routes.append({"route": route, "score_info": score_info})

    if not all_routes:
        return {"plans": [], "matrix": matrix}

    if duration_limit:
        time_limit_s = (duration_limit + 60) * 60
        filtered = [r for r in all_routes if r["score_info"]["total_duration_s"] <= time_limit_s]
        if filtered:
            all_routes = filtered
        else:
            all_routes = sorted(all_routes, key=lambda r: r["score_info"]["total_duration_s"])[: max(80, len(all_routes) // 5)]

    budget = constraints.get("budget")
    budget_limit = _budget_limit(constraints)
    if budget_limit:
        budget_fit = [r for r in all_routes if r["score_info"]["total_cost"] <= budget_limit]
        if budget_fit:
            all_routes = budget_fit

    results = []

    def add_plan(name: str, style: str, route_item: dict, highlights: list[str], allow_similar: bool = False):
        required_stops = min(_min_single_day_stops(constraints), len(_dedupe_route(candidates)))
        display_route = _order_route_for_day_flow(route_item["route"], matrix)
        display_route = _repair_route_composition(display_route, candidates, constraints, style)
        display_route = _trim_route_to_budget(display_route, constraints)
        display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
        display_route = _order_route_for_day_flow(display_route, matrix)
        display_route = _repair_route_composition(display_route, candidates, constraints, style)
        display_route = _trim_route_to_budget(display_route, constraints)
        display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
        display_route = _order_route_for_day_flow(display_route, matrix)
        display_route = _repair_route_composition(display_route, candidates, constraints, style)
        display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
        existing_routes = [r["route"] for r in results]
        if _is_same_order(display_route, existing_routes) or _is_same_stop_set(display_route, existing_routes):
            display_route = _make_route_distinct(display_route, candidates, existing_routes, style)
            display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
            display_route = _repair_route_composition(_order_route_for_day_flow(display_route, matrix), candidates, constraints, style)
            display_route = _trim_route_to_budget(display_route, constraints)
            display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
        display_route = _repair_route_composition(_order_route_for_day_flow(display_route, matrix), candidates, constraints, style)
        display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
        display_route = _trim_route_to_budget(_order_route_for_day_flow(display_route, matrix), constraints)
        if not _is_usable_single_day_route(display_route, required_stops):
            display_route = _make_route_distinct(display_route, candidates, existing_routes, style)
            display_route = _repair_route_composition(_order_route_for_day_flow(display_route, matrix), candidates, constraints, style)
            display_route = _fill_single_day_density(display_route, candidates, constraints, required_stops, style)
            display_route = _trim_route_to_budget(_order_route_for_day_flow(display_route, matrix), constraints)
        if not _is_usable_single_day_route(display_route, required_stops):
            return
        display_score = calculate_route_score(display_route, matrix, constraints)
        if not _within_budget(display_route, constraints):
            return
        existing_routes = [r["route"] for r in results]
        if _is_same_order(display_route, existing_routes) or _is_same_stop_set(display_route, existing_routes):
            return
        if not allow_similar and _is_too_similar(display_route, existing_routes):
            return
        results.append({
            "name": name,
            "style": style,
            "route": _clean_route(display_route),
            "score": display_score,
            "highlights": highlights,
        })

    def budget_aware_primary_key(item: dict) -> tuple[float, float]:
        score = item["score_info"]["route_score"]
        if not budget:
            return score, 0
        cost = item["score_info"].get("total_cost", 0)
        if cost > budget:
            return score - 20, -cost
        target_ratio = float(constraints.get("budget_target_ratio") or 0.78)
        utilization = cost / max(budget, 1)
        target_fit = 1 - abs(utilization - target_ratio)
        return score + target_fit * 2.6, utilization

    best = max(all_routes, key=budget_aware_primary_key)
    add_plan("综合推荐", "balanced", best, ["偏好匹配", "预算利用适中", "类型丰富"])

    walking = _route_item_from_direct_selection(
        _direct_style_route(candidates, route_len, "short_walk", constraints),
        matrix,
        constraints,
    ) or min(
        all_routes,
        key=lambda x: (x["score_info"]["total_distance_m"], -x["score_info"]["route_score"]),
    )
    add_plan("少走路", "short_walk", walking, ["地点更集中", "步行距离更短"])

    food_fun = _route_item_from_direct_selection(
        _direct_style_route(candidates, route_len, "food_fun", constraints),
        matrix,
        constraints,
    ) or max(
        all_routes,
        key=lambda x: (
            _category_hits(x["route"], {"餐厅", "甜品", "咖啡", "购物", "夜景", "娱乐"}),
            x["score_info"]["total_poi_score"],
            -x["score_info"]["total_distance_m"],
        ),
    )
    add_plan("吃好玩好", "food_fun", food_fun, ["餐饮和消费体验更完整", "适合逛吃"])

    if constraints.get("budget_level") in {"comfort", "premium"}:
        premium = _route_item_from_direct_selection(
            _direct_style_route(candidates, route_len, "premium", constraints),
            matrix,
            constraints,
        ) or max(
            all_routes,
            key=lambda x: (
                x["score_info"]["total_cost"],
                _category_hits(x["route"], {"餐厅", "购物", "娱乐", "夜景"}),
                x["score_info"]["total_poi_score"],
            ),
        )
        add_plan("预算充分", "premium", premium, ["提高预算利用", "升级餐饮和体验"])

    low_budget = _route_item_from_direct_selection(
        _direct_style_route(candidates, route_len, "budget", constraints),
        matrix,
        constraints,
    ) or min(
        all_routes,
        key=lambda x: (x["score_info"]["total_cost"], x["score_info"]["total_distance_m"], -x["score_info"]["route_score"]),
    )
    add_plan("省钱轻量", "budget", low_budget, ["低消费", "保留核心体验"])

    # 如果风格方案因相似度被过滤，补充差异最大的高分路线。
    sorted_routes = sorted(all_routes, key=lambda x: x["score_info"]["route_score"], reverse=True)
    for item in sorted_routes:
        if len(results) >= 4:
            break
        add_plan(f"备选方案{len(results) + 1}", "alternative", item, ["补充选择"])

    if len(results) < 3 and candidates:
        supplemental_specs = [
            ("兴趣强化", "food_fun", ["强化偏好", "增加体验点"]),
            ("轻松探索", "short_walk", ["少折返", "节奏更轻"]),
            ("预算稳妥", "budget", ["控制花费", "保留核心体验"]),
            ("备选方案", "alternative", ["补充选择"]),
        ]
        for offset in range(len(candidates)):
            if len(results) >= 3:
                break
            rotated_candidates = candidates[offset:] + candidates[:offset]
            for base_name, style, highlights in supplemental_specs:
                if len(results) >= 3:
                    break
                route = _direct_style_route(rotated_candidates, route_len, style, constraints)
                route = _make_route_distinct(route, candidates, [item["route"] for item in results], style)
                route_item = _route_item_from_direct_selection(route, matrix, constraints)
                if not route_item:
                    continue
                name = base_name if base_name not in {item["name"] for item in results} else f"{base_name}{len(results) + 1}"
                add_plan(name, style, route_item, highlights, allow_similar=True)

    if not results and budget:
        cheapest = min(all_routes, key=lambda x: (x["score_info"]["total_cost"], x["score_info"]["total_distance_m"]))
        display_route = _trim_route_to_budget(_order_route_for_day_flow(cheapest["route"], matrix), constraints)
        if len(display_route) >= 2 and _within_budget(display_route, constraints):
            results.append({
                "name": "综合推荐",
                "style": "balanced",
                "route": _clean_route(display_route),
                "score": calculate_route_score(display_route, matrix, constraints),
                "highlights": ["预算内优先", "保留核心体验"],
            })

    return {"plans": results, "matrix": matrix}


def _route_item_from_direct_selection(route: list[dict], matrix: dict, constraints: dict) -> dict | None:
    if len(route) < 2:
        return None
    return {"route": route, "score_info": calculate_route_score(route, matrix, constraints)}


def _trim_route_to_budget(route: list[dict], constraints: dict) -> list[dict]:
    budget_limit = _budget_limit(constraints)
    if not budget_limit:
        return route
    people_count = max(1, int(constraints.get("people_count") or 1))
    per_person_day_budget = budget_limit / max(1, people_count) / max(1, int(constraints.get("trip_days") or 1))
    if per_person_day_budget <= 90:
        min_stops = 3
    elif per_person_day_budget <= 160:
        min_stops = 4
    else:
        min_stops = 5 if (constraints.get("duration_minutes") or 0) >= 420 else 4
    trimmed = list(route)

    def total_cost(items: list[dict]) -> float:
        return sum(_effective_unit_cost(poi) * people_count for poi in items)

    def remove_costliest() -> None:
        removable = max(
            trimmed,
            key=lambda p: (
                _effective_unit_cost(p) * people_count,
                1 if p.get("category") == "餐厅" else 0,
                -p.get("_score", 0),
            ),
        )
        trimmed.remove(removable)

    while total_cost(trimmed) > budget_limit and len(trimmed) > min_stops:
        remove_costliest()
    while total_cost(trimmed) > budget_limit and len(trimmed) > 2:
        remove_costliest()
    return trimmed


def _min_single_day_stops(constraints: dict) -> int:
    duration = int(constraints.get("duration_minutes") or 0)
    if duration >= 480:
        return 6
    if duration >= 240:
        return 4
    return 4 if not duration else 3


def _fill_single_day_density(
    route: list[dict],
    candidates: list[dict],
    constraints: dict,
    min_stops: int,
    style: str,
) -> list[dict]:
    selected = _dedupe_route(route)
    if len(selected) >= min_stops:
        return selected

    budget_limit = _budget_limit(constraints)
    people_count = max(1, int(constraints.get("people_count") or 1))
    selected_ids = {p.get("id") for p in selected}
    selected_names = {_normalize_route_name(p.get("name", "")) for p in selected}
    food_categories = FOOD_CATEGORIES
    activity_categories = ACTIVITY_CATEGORIES
    prefs = set(constraints.get("preferences") or [])

    def total_cost(items: list[dict]) -> float:
        return sum(_effective_unit_cost(poi) * people_count for poi in items)

    def food_count(items: list[dict]) -> int:
        return sum(1 for p in items if p.get("category") in food_categories)

    def restaurant_count(items: list[dict]) -> int:
        return sum(1 for p in items if p.get("category") == "餐厅")

    def preference_rank(poi: dict) -> int:
        category = poi.get("category")
        if any(PREFERENCE_CATEGORY_BONUS.get(pref, {}).get(category, 0) >= 0.14 for pref in prefs):
            return 0
        if "夜景" in prefs and category in {"夜景", "娱乐"}:
            return 0
        if "游戏" in prefs and category == "娱乐":
            return 0
        if "购物" in prefs and category == "购物":
            return 0
        if category in activity_categories:
            return 1
        return 2

    remaining = [
        p for p in candidates
        if p.get("id") not in selected_ids and _normalize_route_name(p.get("name", "")) not in selected_names
    ]
    remaining.sort(key=lambda p: (preference_rank(p), p.get("category") in food_categories, -p.get("_score", 0)))

    current_cost = total_cost(selected)
    for poi in remaining:
        if len(selected) >= min_stops:
            break
        if _route_family_key(poi) in {_route_family_key(item) for item in selected}:
            continue
        if poi.get("category") == "餐厅" and restaurant_count(selected) >= 1:
            continue
        if poi.get("category") in food_categories and food_count(selected) >= 2:
            continue
        poi_cost = _effective_unit_cost(poi) * people_count
        if budget_limit and current_cost + poi_cost > budget_limit:
            continue
        selected.append(poi)
        selected_ids.add(poi.get("id"))
        selected_names.add(_normalize_route_name(poi.get("name", "")))
        current_cost += poi_cost

    if len(selected) < min_stops:
        for poi in remaining:
            if len(selected) >= min_stops:
                break
            if poi.get("id") in selected_ids or _normalize_route_name(poi.get("name", "")) in selected_names:
                continue
            if _route_family_key(poi) in {_route_family_key(item) for item in selected}:
                continue
            if poi.get("category") == "餐厅" and restaurant_count(selected) >= 1:
                continue
            if poi.get("category") in food_categories and food_count(selected) >= 2:
                continue
            poi_cost = _effective_unit_cost(poi) * people_count
            if budget_limit and current_cost + poi_cost > budget_limit:
                continue
            selected.append(poi)
            selected_ids.add(poi.get("id"))
            selected_names.add(_normalize_route_name(poi.get("name", "")))
            current_cost += poi_cost

    return _dedupe_route(selected)


def _repair_route_composition(route: list[dict], candidates: list[dict], constraints: dict, style: str) -> list[dict]:
    route = _dedupe_route(route)
    if not route:
        return route

    prefs = set(constraints.get("preferences") or [])
    food_categories = FOOD_CATEGORIES
    activity_categories = ACTIVITY_CATEGORIES
    selected_ids = {poi["id"] for poi in route}
    selected_families = {_route_family_key(poi) for poi in route}

    def best_from(categories: set[str], prefer_cost: bool = False) -> dict | None:
        pool = [
            p for p in candidates
            if p["id"] not in selected_ids
            and _route_family_key(p) not in selected_families
            and p.get("category") in categories
        ]
        if not pool:
            return None
        if prefer_cost or style == "premium":
            pool.sort(key=_premium_sort_key, reverse=True)
        else:
            pool.sort(key=lambda p: p.get("_score", 0), reverse=True)
        return pool[0]

    def replace_one(replacement: dict, avoid_categories: set[str] | None = None) -> None:
        avoid_categories = avoid_categories or set()
        replaceable = [
            (idx, poi)
            for idx, poi in enumerate(route)
            if poi.get("category") not in avoid_categories
        ]
        if not replaceable:
            replaceable = list(enumerate(route))
        idx, old = min(replaceable, key=lambda item: (item[1].get("_score", 0), _effective_unit_cost(item[1])))
        selected_ids.discard(old["id"])
        selected_families.discard(_route_family_key(old))
        route[idx] = replacement
        selected_ids.add(replacement["id"])
        selected_families.add(_route_family_key(replacement))

    needs_meal = "美食" in prefs or (constraints.get("duration_minutes") or 0) >= 360 or style in {"food_fun", "premium"}
    if needs_meal and not any(p.get("category") == "餐厅" for p in route):
        restaurant = best_from({"餐厅"}, prefer_cost=style in {"food_fun", "premium"})
        if restaurant:
            replace_one(restaurant, avoid_categories={"景点", "展览", "公园", "夜景", "娱乐"})

    if (prefs & {"夜景", "热闹", "娱乐", "游戏"} or style in {"food_fun", "premium"}) and not any(
        p.get("category") in {"夜景", "娱乐"} for p in route
    ):
        night_or_fun = best_from({"夜景", "娱乐"}, prefer_cost=style == "premium")
        if night_or_fun:
            replace_one(night_or_fun, avoid_categories={"餐厅", "景点", "展览"})

    if "游戏" in prefs and not any(p.get("category") == "娱乐" for p in route):
        game_stop = best_from({"娱乐"}, prefer_cost=style in {"food_fun", "premium"})
        if game_stop:
            replace_one(game_stop, avoid_categories={"餐厅"})

    max_food = 2
    while sum(1 for p in route if p.get("category") in food_categories) > max_food:
        replacement = best_from(activity_categories, prefer_cost=style == "premium")
        if not replacement:
            food_items = [(idx, poi) for idx, poi in enumerate(route) if poi.get("category") in food_categories]
            if len(food_items) > max_food:
                idx, old = min(food_items, key=lambda item: item[1].get("_score", 0))
                selected_ids.discard(old["id"])
                selected_families.discard(_route_family_key(old))
                route.pop(idx)
                continue
            break
        food_items = [(idx, poi) for idx, poi in enumerate(route) if poi.get("category") in food_categories and poi.get("category") != "餐厅"]
        if not food_items:
            food_items = [(idx, poi) for idx, poi in enumerate(route) if poi.get("category") in food_categories]
        idx, old = min(food_items, key=lambda item: item[1].get("_score", 0))
        selected_ids.discard(old["id"])
        selected_families.discard(_route_family_key(old))
        route[idx] = replacement
        selected_ids.add(replacement["id"])
        selected_families.add(_route_family_key(replacement))

    max_restaurants = 1
    while sum(1 for p in route if p.get("category") == "餐厅") > max_restaurants:
        replacement = best_from(activity_categories, prefer_cost=style == "premium")
        if not replacement:
            restaurant_items = [(idx, poi) for idx, poi in enumerate(route) if poi.get("category") == "餐厅"]
            if len(restaurant_items) > max_restaurants:
                idx, old = min(restaurant_items, key=lambda item: item[1].get("_score", 0))
                selected_ids.discard(old["id"])
                selected_families.discard(_route_family_key(old))
                route.pop(idx)
                continue
            break
        restaurant_items = [(idx, poi) for idx, poi in enumerate(route) if poi.get("category") == "餐厅"]
        idx, old = min(restaurant_items, key=lambda item: item[1].get("_score", 0))
        selected_ids.discard(old["id"])
        selected_families.discard(_route_family_key(old))
        route[idx] = replacement
        selected_ids.add(replacement["id"])
        selected_families.add(_route_family_key(replacement))

    min_activity = 2 if len(route) >= 4 else 1
    if prefs & {"游戏", "娱乐", "夜景", "热闹"}:
        min_activity = min(3, max(min_activity, 2))
    while sum(1 for p in route if p.get("category") in activity_categories) < min_activity:
        replacement = best_from(activity_categories, prefer_cost=style == "premium")
        if not replacement:
            break
        replaceable = [
            (idx, poi)
            for idx, poi in enumerate(route)
            if poi.get("category") in food_categories
        ] or [
            (idx, poi)
            for idx, poi in enumerate(route)
            if poi.get("category") not in activity_categories
        ]
        if not replaceable:
            break
        idx, old = min(replaceable, key=lambda item: item[1].get("_score", 0))
        selected_ids.discard(old["id"])
        selected_families.discard(_route_family_key(old))
        route[idx] = replacement
        selected_ids.add(replacement["id"])
        selected_families.add(_route_family_key(replacement))

    return _dedupe_route(route)


def _make_route_distinct(route: list[dict], candidates: list[dict], existing_routes: list[list[dict]], style: str) -> list[dict]:
    if not route:
        return route
    current_ids = {poi["id"] for poi in route}
    replacements = [poi for poi in candidates if poi["id"] not in current_ids]
    if style == "budget":
        replacements.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
    elif style == "food_fun":
        replacements.sort(key=lambda p: (p.get("category") not in {"餐厅", "咖啡", "甜品", "购物", "娱乐", "夜景"}, -p.get("_score", 0)))
    else:
        replacements.sort(key=lambda p: p.get("_score", 0), reverse=True)

    for replacement in replacements:
        for idx in range(len(route) - 1, -1, -1):
            candidate_route = list(route)
            candidate_route[idx] = replacement
            candidate_route = _order_route_for_day_flow(_dedupe_route(candidate_route), {})
            if not _is_same_order(candidate_route, existing_routes) and not _is_same_stop_set(candidate_route, existing_routes):
                return candidate_route
    return route


def _make_multiday_route_distinct(
    route: list[dict],
    candidates: list[dict],
    existing_routes: list[list[dict]],
    style: str,
    target_len: int,
) -> list[dict]:
    if not route:
        return route

    current_ids = {poi["id"] for poi in route}
    pool = [poi for poi in candidates if poi["id"] not in current_ids]
    if style in {"premium", "food_fun"}:
        pool.sort(key=lambda p: (_effective_unit_cost(p), p.get("_score", 0)), reverse=True)
    elif style in {"light", "budget"}:
        pool.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
    elif style in {"compact", "short_walk"}:
        pool.sort(key=lambda p: p.get("_score", 0), reverse=True)
    else:
        pool.sort(key=lambda p: p.get("_score", 0), reverse=True)

    existing_sets = [{poi["id"] for poi in existing} for existing in existing_routes]
    replace_positions = list(range(len(route) - 1, -1, -1))
    if style in {"premium", "food_fun"}:
        replace_positions = list(range(len(route)))

    for replacement in pool:
        for idx in replace_positions:
            trial = list(route)
            trial[idx] = replacement
            trial = _dedupe_route(trial)
            if len(trial) < min(3, target_len):
                continue
            trial_ids = {poi["id"] for poi in trial}
            if all(len(trial_ids & existing) / max(len(trial_ids | existing), 1) < 0.92 for existing in existing_sets):
                return trial

    if len(route) > 3:
        shift = max(1, len(existing_routes) % len(route))
        return route[shift:] + route[:shift]
    return route


def _direct_style_route(candidates: list[dict], target_len: int, style: str, constraints: dict | None = None) -> list[dict]:
    if not candidates or target_len <= 0:
        return []

    selected: list[dict] = []
    seen: set[str] = set()
    seen_families: set[str] = set()

    def add_from(category: str, count: int = 1, reverse_cost: bool = False):
        bucket = [
            p for p in candidates
            if p.get("category") == category
            and p["id"] not in seen
            and _route_family_key(p) not in seen_families
        ]
        if style == "budget":
            bucket.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
        elif reverse_cost:
            bucket.sort(key=_premium_sort_key, reverse=True)
        else:
            bucket.sort(key=lambda p: p.get("_score", 0), reverse=True)
        for poi in bucket[:count]:
            if len(selected) >= target_len:
                return
            selected.append(poi)
            seen.add(poi["id"])
            seen_families.add(_route_family_key(poi))

    prefs = set((constraints or {}).get("preferences") or [])
    recipe = next((PREFERENCE_STYLE_RECIPES[pref] for pref in PREFERENCE_STYLE_RECIPES if pref in prefs), None)

    if recipe and style in {"food_fun", "premium", "budget"}:
        for category, count in recipe:
            adjusted_count = count
            if category == "餐厅" and target_len < 7:
                adjusted_count = 1
            add_from(category, adjusted_count, reverse_cost=style in {"food_fun", "premium"} and category in {"餐厅", "购物", "娱乐", "夜景"})
    elif style == "food_fun":
        for category, count in [("餐厅", 1), ("娱乐", 1), ("夜景", 1), ("购物", 1), ("咖啡", 1), ("景点", 1), ("展览", 1), ("甜品", 1)]:
            add_from(category, count, reverse_cost=category in {"餐厅", "购物", "娱乐"})
    elif style == "premium":
        for category, count in [("景点", 1), ("展览", 1), ("餐厅", 1), ("购物", 1), ("娱乐", 1), ("夜景", 1), ("咖啡", 1), ("公园", 1), ("甜品", 1)]:
            add_from(category, count, reverse_cost=category in {"餐厅", "购物", "娱乐", "夜景"})
    elif style == "budget":
        for category in ["公园", "展览", "景点", "咖啡", "甜品", "餐厅", "购物", "娱乐", "夜景"]:
            add_from(category)
    elif style == "short_walk":
        ordered = _order_route_nearest(candidates, build_route_matrix(candidates[: min(len(candidates), 10)]))
        for poi in ordered:
            family_key = _route_family_key(poi)
            if poi["id"] not in seen and family_key not in seen_families and len(selected) < target_len:
                selected.append(poi)
                seen.add(poi["id"])
                seen_families.add(family_key)

    remaining = [p for p in candidates if p["id"] not in seen]
    remaining.sort(key=lambda p: p.get("_score", 0), reverse=True)
    food_categories = {"餐厅", "咖啡", "甜品"}

    def can_append(poi: dict) -> bool:
        if _route_family_key(poi) in seen_families:
            return False
        if poi.get("category") == "餐厅" and any(item.get("category") == "餐厅" for item in selected):
            return False
        if poi.get("category") in food_categories and sum(1 for item in selected if item.get("category") in food_categories) >= 2:
            return False
        return True

    for poi in remaining:
        if len(selected) >= target_len:
            break
        if not can_append(poi):
            continue
        selected.append(poi)
        seen.add(poi["id"])
        seen_families.add(_route_family_key(poi))
    return selected[:target_len]


def _parse_center(area_center: tuple | str | None) -> tuple[float, float] | None:
    if not area_center:
        return None
    if isinstance(area_center, str) and "," in area_center:
        lng, lat = area_center.split(",", 1)
        return float(lng), float(lat)
    if isinstance(area_center, (list, tuple)) and len(area_center) == 2:
        return float(area_center[0]), float(area_center[1])
    return None


def _optimize_multiday_route(pois: list[dict], constraints: dict, trip_days: int, area_center: tuple = None) -> dict:
    target_stops = min(len(pois), max(trip_days * 6, min(trip_days * 7, 42)))
    candidates = _bucket_and_select(pois, max_stops=target_stops, hard_limit=min(max(target_stops + 16, 24), 64))
    matrix = build_route_matrix(candidates, constraints.get("transport_mode", "walking"))
    start_center = _parse_center(constraints.get("start_location")) or area_center

    routes = []
    selected_balanced = _select_candidates_by_style(candidates, constraints, target_stops, "balanced")
    routes.append(("多日综合", "balanced", selected_balanced, ["按天拆分", "类型均衡", "转场顺序优化"], target_stops))

    selected_premium = _select_candidates_by_style(candidates, constraints, target_stops, "premium")
    routes.append(("预算充分", "premium", selected_premium, ["提高预算利用", "更多餐饮与体验消费", "适合不想太省"], target_stops))

    compact_target = max(5, target_stops - trip_days)
    selected_compact = _select_candidates_by_style(candidates, constraints, compact_target, "compact")
    routes.append(("少折返", "compact", selected_compact, ["减少跨城折返", "每天集中片区"], compact_target))

    light_target = max(5, target_stops - trip_days)
    selected_light = _select_candidates_by_style(candidates, constraints, light_target, "light")
    routes.append(("轻松留白", "relaxed", selected_light, ["每天不过载", "留出临时活动和休息时间"], light_target))

    results = []
    for name, style, route, highlights, route_target in routes:
        route = _fill_route_to_budget(_dedupe_route(route), candidates, constraints, route_target)
        ordered = _order_multiday_route(route, matrix, trip_days, start_center)
        if len(ordered) < 3:
            continue
        score_info = calculate_route_score(ordered, matrix, constraints)
        if _is_same_order(ordered, [r["route"] for r in results]):
            route = _make_multiday_route_distinct(route, candidates, [r["route"] for r in results], style, route_target)
            ordered = _order_multiday_route(route, matrix, trip_days, start_center)
            if len(ordered) >= 3 and _is_same_order(ordered, [r["route"] for r in results]):
                ordered = _rotate_route_order(ordered, len(results) + 1)
            if len(ordered) < 3 or _is_same_order(ordered, [r["route"] for r in results]):
                continue
        score_info = calculate_route_score(ordered, matrix, constraints)
        if not _within_budget(ordered, constraints):
            continue
        results.append({
            "name": name,
            "style": style,
            "route": _clean_route(ordered),
            "score": score_info,
            "highlights": highlights,
        })

    if not results:
        ordered = _order_multiday_route(candidates[:target_stops], matrix, trip_days, start_center)
        if _within_budget(ordered, constraints):
            results.append({
                "name": "多日综合",
                "style": "balanced",
                "route": _clean_route(ordered),
                "score": calculate_route_score(ordered, matrix, constraints),
                "highlights": ["按天拆分"],
            })

    budget = constraints.get("budget")
    budget_limit = _budget_limit(constraints)
    if budget_limit:
        feasible = [r for r in results if r["score"].get("total_cost", 0) <= budget_limit]
        target_ratio = float(constraints.get("budget_target_ratio") or 0.82)
        if feasible:
            sorted_feasible = sorted(
                feasible,
                key=lambda r: (
                    -len(r["route"]),
                    abs((r["score"].get("total_cost", 0) / budget) - target_ratio),
                    -r["score"].get("route_score", 0),
                ),
            )
            supplemental = [r for r in results if r not in sorted_feasible and r["score"].get("total_cost", 0) <= budget_limit]
            results = sorted_feasible + supplemental
        else:
            results = []

    if len(results) < 4 and candidates:
        fallback_specs = [
            ("兴趣强化", "premium", target_stops, ["强化偏好", "提高体验质量"]),
            ("性价比补充", "light", max(5, target_stops - trip_days), ["控制花费", "保留核心体验"]),
            ("紧凑探索", "compact", max(5, target_stops - trip_days), ["减少折返", "片区更集中"]),
            ("备选方案", "balanced", target_stops, ["补充选择"]),
        ]
        for name, style, route_target, highlights in fallback_specs:
            if len(results) >= 4:
                break
            route = _select_candidates_by_style(candidates, constraints, route_target, style)
            route = _fill_route_to_budget(_dedupe_route(route), candidates, constraints, route_target)
            route = _make_multiday_route_distinct(route, candidates, [r["route"] for r in results], style, route_target)
            ordered = _order_multiday_route(route, matrix, trip_days, start_center)
            if len(ordered) >= 3 and _is_same_order(ordered, [r["route"] for r in results]):
                ordered = _rotate_route_order(ordered, len(results) + 1)
            if len(ordered) < 3 or _is_same_order(ordered, [r["route"] for r in results]):
                continue
            if not _within_budget(ordered, constraints):
                continue
            results.append({
                "name": name if name not in {r["name"] for r in results} else f"{name}{len(results) + 1}",
                "style": style,
                "route": _clean_route(ordered),
                "score": calculate_route_score(ordered, matrix, constraints),
                "highlights": highlights,
            })

    return {"plans": results[:4], "matrix": matrix}


def _filter_by_trip_radius(pois: list[dict], constraints: dict, center: tuple[float, float] | None) -> list[dict]:
    if not center:
        return pois
    preferences = set(constraints.get("preferences") or [])
    trip_days = max(1, int(constraints.get("trip_days") or 1))
    radius_m = 42000 if preferences & {"爬山", "户外", "运动"} else 18000 if trip_days <= 2 else 22000
    filtered = []
    for poi in pois:
        if poi.get("lng") is None or poi.get("lat") is None:
            filtered.append(poi)
            continue
        distance = haversine_distance(float(poi["lng"]), float(poi["lat"]), center[0], center[1])
        if distance <= radius_m:
            filtered.append(poi)
    return filtered if len(filtered) >= min(12, len(pois)) else pois


def _fill_route_to_budget(route: list[dict], candidates: list[dict], constraints: dict, target_stops: int) -> list[dict]:
    budget_limit = _budget_limit(constraints)
    if not budget_limit or len(route) >= target_stops:
        return route

    people_count = max(1, int(constraints.get("people_count") or 1))
    food_categories = {"餐厅", "咖啡", "甜品"}
    activity_categories = {"景点", "展览", "公园", "购物", "娱乐", "夜景"}
    selected = _dedupe_route(route)

    def route_cost(items: list[dict]) -> float:
        return sum(_effective_unit_cost(p) * people_count for p in items)

    def food_count(items: list[dict]) -> int:
        return sum(1 for p in items if p.get("category") in food_categories)

    current_cost = route_cost(selected)
    budget_cap = budget_limit
    selected_names = {_normalize_route_name(p.get("name", "")) for p in selected}
    selected_ids = {p.get("id") for p in selected}
    food_limit = 2

    remaining = [
        p for p in candidates
        if p.get("id") not in selected_ids and _normalize_route_name(p.get("name", "")) not in selected_names
    ]
    remaining.sort(
        key=lambda p: (
            p.get("category") not in activity_categories,
            p.get("category") in food_categories,
            _effective_unit_cost(p),
            -p.get("_score", 0),
        )
    )

    for poi in remaining:
        if len(selected) >= target_stops:
            break
        if poi.get("category") in food_categories and food_count(selected) >= food_limit:
            continue
        poi_cost = _effective_unit_cost(poi) * people_count
        if current_cost + poi_cost > budget_cap:
            continue
        selected.append(poi)
        selected_ids.add(poi.get("id"))
        selected_names.add(_normalize_route_name(poi.get("name", "")))
        current_cost += poi_cost

    return _dedupe_route(selected)


def _select_candidates_by_style(candidates: list[dict], constraints: dict, target_stops: int, style: str) -> list[dict]:
    people_count = max(1, int(constraints.get("people_count") or 1))
    budget = constraints.get("budget") or 0
    trip_days = max(1, int(constraints.get("trip_days") or 1))
    target_ratio = float(constraints.get("budget_target_ratio") or 0.78)
    if style == "premium":
        style_ratio = min(0.98, max(0.86, target_ratio + 0.10))
    elif style == "balanced":
        style_ratio = target_ratio
    elif style == "compact":
        style_ratio = max(0.58, target_ratio - 0.16)
    else:
        style_ratio = max(0.42, target_ratio - 0.28)
    target_cost = budget * style_ratio
    persona_order = (constraints.get("persona_strategy") or {}).get("category_order") or []
    categories_order = list(dict.fromkeys(persona_order + ["景点", "展览", "公园", "购物", "娱乐", "夜景", "餐厅", "咖啡", "甜品"]))
    buckets: dict[str, list[dict]] = {}
    for poi in candidates:
        buckets.setdefault(poi.get("category", "其他"), []).append(poi)

    for category, bucket in buckets.items():
        if style == "premium":
            bucket.sort(key=_premium_sort_key, reverse=True)
        elif style == "light":
            bucket.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
        else:
            bucket.sort(key=lambda p: p.get("_score", 0), reverse=True)

    selected = []
    seen = set()

    def take_from(category_options: list[str], reverse_cost: bool = False) -> bool:
        best_category = None
        best_poi = None
        for category in category_options:
            bucket = [p for p in buckets.get(category, []) if p["id"] not in seen]
            if not bucket:
                continue
            if style == "premium" or reverse_cost:
                bucket.sort(key=_premium_sort_key, reverse=True)
            elif style == "light":
                bucket.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
            else:
                bucket.sort(key=lambda p: p.get("_score", 0), reverse=True)
            if best_poi is None or bucket[0].get("_score", 0) > best_poi.get("_score", 0):
                best_category = category
                best_poi = bucket[0]
        if not best_poi or len(selected) >= target_stops:
            return False
        selected.append(best_poi)
        seen.add(best_poi["id"])
        if best_category in buckets:
            buckets[best_category] = [p for p in buckets[best_category] if p["id"] != best_poi["id"]]
        return True

    if trip_days > 1:
        day_templates = {
            "premium": [
                ["景点", "展览", "公园"],
                ["餐厅"],
                ["娱乐", "购物", "景点"],
                ["夜景", "咖啡", "甜品"],
                ["展览", "公园", "购物"],
                ["夜景", "娱乐", "购物"],
            ],
            "light": [
                ["公园", "景点"],
                ["展览", "景点"],
                ["餐厅"],
                ["咖啡", "甜品"],
                ["购物", "夜景", "娱乐"],
            ],
        }.get(style, [
            ["景点", "展览", "公园"],
            ["餐厅"],
            ["娱乐", "购物", "景点"],
            ["夜景", "咖啡", "甜品"],
            ["展览", "公园", "夜景"],
            ["夜景", "娱乐", "购物"],
        ])
        while len(selected) < target_stops and any(buckets.values()):
            before = len(selected)
            for slot in day_templates:
                if len(selected) >= target_stops:
                    break
                take_from(slot, reverse_cost=style == "premium" and slot[0] in {"餐厅", "购物", "娱乐"})
            if len(selected) == before:
                break

    while len(selected) < target_stops and any(buckets.values()):
        progressed = False
        for category in categories_order:
            bucket = buckets.get(category)
            if not bucket:
                continue
            poi = bucket.pop(0)
            if poi["id"] in seen:
                continue
            selected.append(poi)
            seen.add(poi["id"])
            progressed = True
            if len(selected) >= target_stops:
                break
        if not progressed:
            break

    remaining = [p for p in candidates if p["id"] not in seen]
    if style == "premium" and budget:
        current_cost = sum(_effective_unit_cost(p) * people_count for p in selected)
        remaining.sort(key=_premium_sort_key, reverse=True)
        for poi in remaining:
            if len(selected) >= target_stops:
                break
            if current_cost < target_cost or poi.get("category") in {"娱乐", "购物", "夜景", "展览"}:
                selected.append(poi)
                current_cost += _effective_unit_cost(poi) * people_count
    else:
        remaining.sort(key=lambda p: p.get("_score", 0), reverse=True)
        selected.extend(remaining[: max(0, target_stops - len(selected))])

    selected = selected[:target_stops]
    if budget:
        cap_ratio = {
            "premium": 1.0,
            "balanced": 1.0,
            "compact": 0.90,
            "light": 0.72,
        }.get(style, 0.98)
        daily_budget = budget / max(1, trip_days)
        dense_day_floor = 5 if daily_budget >= people_count * 120 else 4
        min_stops = min(
            target_stops,
            max(5, trip_days * (dense_day_floor if style in {"balanced", "premium"} else 3)),
        )
        selected = _fit_route_to_budget(selected, candidates, people_count, budget * cap_ratio, min_stops, target_stops)
        if style == "premium":
            selected = _raise_budget_use(selected, candidates, people_count, budget * min(0.96, max(0.86, target_ratio + 0.08)), budget * cap_ratio, target_stops)

    return selected[:target_stops]


def _fit_route_to_budget(
    selected: list[dict],
    candidates: list[dict],
    people_count: int,
    budget_cap: float,
    min_stops: int,
    target_stops: int,
) -> list[dict]:
    """Keep multi-day routes close to budget instead of blindly filling every slot."""
    selected = _dedupe_route(selected)
    selected_ids = {p["id"] for p in selected}

    def route_cost(route: list[dict]) -> float:
        return sum(_effective_unit_cost(p) * people_count for p in route)

    selected = _replace_costly_stops_for_budget(selected, candidates, people_count, budget_cap)
    selected_ids = {p["id"] for p in selected}

    budget_floor = max(5, min_stops - max(2, target_stops // 5))
    while route_cost(selected) > budget_cap and len(selected) > budget_floor:
        removable = max(
            selected,
            key=lambda p: (_effective_unit_cost(p) * people_count, -p.get("_score", 0)),
        )
        selected.remove(removable)
        selected_ids.discard(removable["id"])

    selected = _replace_costly_stops_for_budget(selected, candidates, people_count, budget_cap)
    selected_ids = {p["id"] for p in selected}
    while route_cost(selected) > budget_cap and len(selected) > budget_floor:
        removable = max(
            selected,
            key=lambda p: (_effective_unit_cost(p) * people_count, -p.get("_score", 0)),
        )
        selected.remove(removable)
        selected_ids.discard(removable["id"])
    while route_cost(selected) > budget_cap and len(selected) > 2:
        removable = max(
            selected,
            key=lambda p: (_effective_unit_cost(p) * people_count, -p.get("_score", 0)),
        )
        selected.remove(removable)
        selected_ids.discard(removable["id"])

    remaining = [p for p in candidates if p["id"] not in selected_ids]
    remaining.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))

    for poi in remaining:
        if len(selected) >= target_stops:
            break
        next_cost = route_cost(selected) + _effective_unit_cost(poi) * people_count
        if next_cost <= budget_cap:
            selected.append(poi)
            selected_ids.add(poi["id"])

    if len(selected) < target_stops:
        selected = _increase_activity_density(selected, candidates, people_count, budget_cap, target_stops)

    return selected[:target_stops]


def _replace_costly_stops_for_budget(
    selected: list[dict],
    candidates: list[dict],
    people_count: int,
    budget_cap: float,
) -> list[dict]:
    selected = _dedupe_route(selected)
    activity_categories = {"景点", "展览", "公园", "购物", "娱乐", "夜景"}

    def route_cost(route: list[dict]) -> float:
        return sum(_effective_unit_cost(p) * people_count for p in route)

    def item_cost(poi: dict) -> float:
        return _effective_unit_cost(poi) * people_count

    for _ in range(len(selected) * 2):
        current_cost = route_cost(selected)
        if current_cost <= budget_cap:
            break

        selected_ids = {p["id"] for p in selected}
        replacement_pool = [p for p in candidates if p["id"] not in selected_ids]
        replacement_pool.sort(
            key=lambda p: (
                p.get("category") not in activity_categories,
                item_cost(p),
                -p.get("_score", 0),
            )
        )
        removable_pool = sorted(selected, key=lambda p: (item_cost(p), -p.get("_score", 0)), reverse=True)

        replaced = False
        for removable in removable_pool:
            removable_cost = item_cost(removable)
            for replacement in replacement_pool:
                replacement_cost = item_cost(replacement)
                if replacement_cost >= removable_cost:
                    continue
                selected[selected.index(removable)] = replacement
                replaced = True
                break
            if replaced:
                break

        if not replaced:
            break

    return _dedupe_route(selected)


def _increase_activity_density(
    selected: list[dict],
    candidates: list[dict],
    people_count: int,
    budget_cap: float,
    target_stops: int,
) -> list[dict]:
    """Replace a few expensive food-heavy stops with cheaper activity pairs."""
    selected = _dedupe_route(selected)
    food_categories = {"餐厅", "咖啡", "甜品"}
    activity_categories = {"景点", "展览", "公园", "购物", "娱乐", "夜景"}

    def route_cost(route: list[dict]) -> float:
        return sum(_effective_unit_cost(p) * people_count for p in route)

    def item_cost(poi: dict) -> float:
        return _effective_unit_cost(poi) * people_count

    while len(selected) < target_stops:
        selected_ids = {p["id"] for p in selected}
        remaining = [p for p in candidates if p["id"] not in selected_ids]
        remaining.sort(
            key=lambda p: (
                p.get("category") not in activity_categories,
                p.get("category") in food_categories,
                item_cost(p),
                -p.get("_score", 0),
            )
        )

        current_cost = route_cost(selected)
        affordable = next((p for p in remaining if current_cost + item_cost(p) <= budget_cap), None)
        if affordable:
            selected.append(affordable)
            continue

        replaceable = [p for p in selected if p.get("category") in food_categories]
        replaceable.sort(key=lambda p: (item_cost(p), p.get("_score", 0)), reverse=True)

        replacement_done = False
        pool = remaining[:40]
        for removable in replaceable:
            removable_cost = item_cost(removable)
            for first_index, first in enumerate(pool):
                for second in pool[first_index + 1:]:
                    pair = [first, second]
                    if all(p.get("category") in food_categories for p in pair):
                        continue
                    next_cost = current_cost - removable_cost + sum(item_cost(p) for p in pair)
                    if next_cost > budget_cap:
                        continue
                    selected.remove(removable)
                    selected.extend(pair)
                    replacement_done = True
                    break
                if replacement_done:
                    break
            if replacement_done:
                break

        if not replacement_done:
            break

    return _dedupe_route(selected)


def _raise_budget_use(
    selected: list[dict],
    candidates: list[dict],
    people_count: int,
    target_cost: float,
    budget_cap: float,
    target_stops: int,
) -> list[dict]:
    selected = _dedupe_route(selected)

    def route_cost(route: list[dict]) -> float:
        return sum(_effective_unit_cost(p) * people_count for p in route)

    selected_ids = {p["id"] for p in selected}
    remaining = [p for p in candidates if p["id"] not in selected_ids]
    remaining.sort(key=_premium_sort_key, reverse=True)

    for poi in remaining:
        current_cost = route_cost(selected)
        if current_cost >= target_cost:
            break
        poi_cost = _effective_unit_cost(poi) * people_count
        if len(selected) < target_stops and current_cost + poi_cost <= budget_cap:
            selected.append(poi)
            selected_ids.add(poi["id"])
            continue

        cheapest = min(selected, key=lambda p: (_effective_unit_cost(p) * people_count, p.get("_score", 0)))
        cheapest_cost = _effective_unit_cost(cheapest) * people_count
        if poi_cost > cheapest_cost and current_cost - cheapest_cost + poi_cost <= budget_cap:
            selected.remove(cheapest)
            selected_ids.discard(cheapest["id"])
            selected.append(poi)
            selected_ids.add(poi["id"])

    return selected


def _order_multiday_route(route: list[dict], matrix: dict, trip_days: int, start_center: tuple | None = None) -> list[dict]:
    """Build a day-by-day sequence so every day has sights/experience, food and a rest point."""
    remaining = _dedupe_route(route)
    if len(remaining) <= 2 or trip_days <= 1:
        return _order_route_nearest(remaining, matrix, start_center)

    day_routes: list[list[dict]] = []
    day_templates = [
        ["公园", "景点", "展览"],
        ["餐厅"],
        ["娱乐", "购物", "景点"],
        ["夜景", "咖啡", "甜品"],
        ["展览", "公园", "购物"],
        ["夜景", "娱乐", "购物"],
    ]
    prev = None

    for day_index in range(1, trip_days + 1):
        if not remaining:
            break
        target_count = math.ceil(len(remaining) / (trip_days - day_index + 1))
        day_pois: list[dict] = []

        while len(day_pois) < target_count and remaining:
            before = len(day_pois)
            for category_options in day_templates:
                if len(day_pois) >= target_count:
                    break
                chosen = _pop_best_from_categories(remaining, category_options, prev or (day_pois[-1] if day_pois else None), matrix)
                if chosen:
                    day_pois.append(chosen)
            if len(day_pois) == before:
                chosen = _pick_nearest_flow_candidate(remaining, prev or (day_pois[-1] if day_pois else None), matrix)
                remaining.remove(chosen)
                day_pois.append(chosen)

        day_ordered = _order_route_for_day_flow(day_pois, matrix)
        if day_ordered:
            prev = day_ordered[-1]
            day_routes.append(day_ordered)

    if remaining:
        day_routes.append(_order_route_for_day_flow(remaining, matrix))

    _rebalance_day_routes(day_routes, matrix)
    return [poi for day in day_routes for poi in day]


def _rebalance_day_routes(day_routes: list[list[dict]], matrix: dict) -> None:
    food_categories = {"餐厅", "咖啡", "甜品"}

    def non_food_count(day: list[dict]) -> int:
        return sum(1 for poi in day if poi.get("category") not in food_categories)

    for day in day_routes:
        if not day or non_food_count(day) > 0:
            continue
        donor = max(
            (candidate for candidate in day_routes if candidate is not day and non_food_count(candidate) >= 2),
            key=non_food_count,
            default=None,
        )
        if not donor:
            continue
        donor_non_food = next((poi for poi in donor if poi.get("category") not in food_categories), None)
        day_food = next((poi for poi in day if poi.get("category") in food_categories), None)
        if not donor_non_food or not day_food:
            continue
        donor[donor.index(donor_non_food)] = day_food
        day[day.index(day_food)] = donor_non_food

    for index, day in enumerate(day_routes):
        day_routes[index] = _order_route_for_day_flow(day, matrix)


def _pop_best_from_categories(
    remaining: list[dict],
    category_options: list[str],
    prev: dict | None,
    matrix: dict,
) -> dict | None:
    candidates = [poi for poi in remaining if poi.get("category") in category_options]
    if not candidates:
        return None
    chosen = _pick_nearest_flow_candidate(candidates, prev, matrix)
    remaining.remove(chosen)
    return chosen


def _order_route_nearest(route: list[dict], matrix: dict, start_center: tuple | None = None) -> list[dict]:
    if len(route) <= 2:
        return route
    remaining = list(route)
    ordered = []

    if start_center:
        first = min(
            remaining,
            key=lambda p: haversine_distance(float(p["lng"]), float(p["lat"]), start_center[0], start_center[1])
            if p.get("lng") is not None and p.get("lat") is not None else 999999,
        )
    else:
        first = max(remaining, key=lambda p: p.get("_score", 0))

    ordered.append(first)
    remaining.remove(first)
    while remaining:
        prev = ordered[-1]
        nxt = min(
            remaining,
            key=lambda p: matrix.get((prev["id"], p["id"]), {}).get("distance_m", 999999) - p.get("_score", 0) * 120,
        )
        ordered.append(nxt)
        remaining.remove(nxt)
    return ordered


def _order_route_for_day_flow(route: list[dict], matrix: dict) -> list[dict]:
    """Order one-day stops by human travel rhythm, then reduce distance inside each slot."""
    if len(route) <= 2:
        return route

    remaining = _dedupe_route(route)
    ordered = []

    for bucket in [1, 2, 3, 4, 5, 6, 7, 8]:
        while True:
            candidates = [poi for poi in remaining if _daily_flow_bucket(poi) == bucket]
            if not candidates:
                break
            chosen = _pick_nearest_flow_candidate(candidates, ordered[-1] if ordered else None, matrix)
            ordered.append(chosen)
            remaining.remove(chosen)

    return ordered


def _pick_nearest_flow_candidate(candidates: list[dict], prev: dict | None, matrix: dict) -> dict:
    if not prev:
        return max(candidates, key=lambda p: p.get("_score", 0))
    return min(
        candidates,
        key=lambda p: matrix.get((prev["id"], p["id"]), {}).get("distance_m", 999999) - p.get("_score", 0) * 160,
    )


def _daily_flow_bucket(poi: dict) -> int:
    category = poi.get("category", "")
    text = f"{poi.get('name', '')} {category} {' '.join(_safe_tags(poi))}".lower()

    if any(word in text for word in ["早茶", "早餐", "brunch", "茶点", "茶楼", "茶餐厅"]):
        return 1
    if category == "夜景" or any(word in text for word in ["夜景", "夜市", "酒吧", "灯光", "演出", "音乐节", "livehouse"]):
        return 7
    if category == "餐厅":
        if any(word in text for word in ["火锅", "海底捞", "烧烤", "烤肉", "牛排", "酒吧", "夜宵", "宵夜", "居酒屋"]):
            return 6
        return 3
    if category in {"景点", "展览", "公园"}:
        return 2
    if category in {"咖啡", "甜品"}:
        return 4
    if category == "购物":
        return 5
    if category == "娱乐":
        return 6
    return 8


def _dedupe_route(route: list[dict]) -> list[dict]:
    result = []
    seen_ids = set()
    seen_names = set()
    seen_families = set()
    for poi in route:
        name_key = _normalize_route_name(poi.get("name", ""))
        family_key = _route_family_key(poi)
        if poi["id"] in seen_ids or name_key in seen_names or family_key in seen_families:
            continue
        result.append(poi)
        seen_ids.add(poi["id"])
        seen_names.add(name_key)
        seen_families.add(family_key)
    return result


def _normalize_route_name(name: str) -> str:
    return "".join(str(name or "").lower().split())


def _route_family_key(poi: dict) -> str:
    """Treat different branches of the same chain as one experience in a route."""
    name = str(poi.get("name") or "")
    category = str(poi.get("category") or "")
    base = re.split(r"[（(\[]", name, maxsplit=1)[0]
    base = re.sub(r"(总店|旗舰店|分店|门店|直营店|体验店|专卖店|加盟店)$", "", base)
    base = re.sub(r"(广州|深圳|上海|北京|杭州|成都|重庆|武汉|南京|苏州|西安|天津|厦门|青岛|佛山|东莞)", "", base)
    base = _normalize_route_name(base)
    if not base:
        base = _normalize_route_name(name)
    return f"{category}:{base}"


def _is_usable_single_day_route(route: list[dict], required_stops: int) -> bool:
    route = _dedupe_route(route)
    if len(route) < required_stops:
        return False
    food_count = sum(1 for poi in route if poi.get("category") in FOOD_CATEGORIES)
    restaurant_count = sum(1 for poi in route if poi.get("category") == "餐厅")
    activity_count = sum(1 for poi in route if poi.get("category") in ACTIVITY_CATEGORIES)
    if restaurant_count > 1:
        return False
    if food_count > 2:
        return False
    if len(route) >= 4 and activity_count < 2:
        return False
    return True


def _bucket_and_select(pois: list[dict], max_stops: int, hard_limit: int = 8, constraints: dict | None = None) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for poi in pois:
        buckets.setdefault(poi.get("category", "其他"), []).append(poi)

    for bucket in buckets.values():
        bucket.sort(key=lambda x: x.get("_score", 0), reverse=True)

    selected = []
    seen_families: set[str] = set()
    preferences = (constraints or {}).get("preferences") or []
    desired = _desired_categories(preferences)
    desired_order = [category for category in ["娱乐", "夜景", "购物", "展览", "景点", "公园", "餐厅", "咖啡", "甜品"] if category in desired]
    persona_order = ((constraints or {}).get("persona_strategy") or {}).get("category_order") or []
    preferred_order = list(dict.fromkeys(
        desired_order
        + persona_order
        + ["娱乐", "夜景", "购物", "展览", "景点", "公园", "餐厅", "咖啡", "甜品"]
    ))
    food_taken = 0
    restaurant_taken = 0
    for category in preferred_order:
        if category in buckets and buckets[category]:
            for index, poi in enumerate(list(buckets[category])):
                if _route_family_key(poi) in seen_families:
                    continue
                if category == "餐厅" and restaurant_taken >= 1:
                    continue
                if category in FOOD_CATEGORIES and food_taken >= 2:
                    continue
                selected.append(poi)
                seen_families.add(_route_family_key(poi))
                food_taken += 1 if category in FOOD_CATEGORIES else 0
                restaurant_taken += 1 if category == "餐厅" else 0
                buckets[category].pop(index)
                break

    remaining = [poi for bucket in buckets.values() for poi in bucket]
    remaining.sort(key=lambda x: x.get("_score", 0), reverse=True)
    selected.extend(remaining)

    deduped = []
    seen = set()
    seen_dedupe_families = set()
    for poi in selected:
        family_key = _route_family_key(poi)
        if poi["id"] in seen or family_key in seen_dedupe_families:
            continue
        deduped.append(poi)
        seen.add(poi["id"])
        seen_dedupe_families.add(family_key)
        if len(deduped) >= max(max_stops + 3, hard_limit):
            break

    return deduped[:hard_limit]


def _category_hits(route: list[dict], categories: set[str]) -> int:
    return sum(1 for poi in route if poi.get("category") in categories)


def _desired_categories(preferences: list[str]) -> set[str]:
    mapping = {
        "美食": {"餐厅", "甜品"},
        "咖啡": {"咖啡"},
        "看展": {"展览"},
        "自然": {"公园", "景点"},
        "爬山": {"公园", "景点"},
        "户外": {"公园", "景点"},
        "运动": {"娱乐", "公园"},
        "游戏": {"娱乐", "购物"},
        "娱乐": {"娱乐", "夜景", "购物"},
        "休闲": {"咖啡", "甜品", "公园", "娱乐"},
        "购物": {"购物"},
        "亲子": {"公园", "展览", "景点"},
        "夜景": {"夜景", "景点"},
        "探店": {"咖啡", "甜品", "购物"},
        "拍照": {"景点", "展览", "咖啡"},
        "历史": {"展览", "景点"},
        "热闹": {"购物", "夜景", "餐厅"},
    }
    desired = set()
    for pref in preferences:
        desired.update(mapping.get(pref, set()))
    return desired


def _is_too_similar(route: list[dict], existing_routes: list[list[dict]]) -> bool:
    current = {poi["id"] for poi in route}
    for existing in existing_routes:
        other = {poi["id"] for poi in existing}
        overlap = len(current & other) / max(len(current | other), 1)
        if overlap >= 0.82:
            return True
    return False


def _is_same_order(route: list[dict], existing_routes: list[list[dict]]) -> bool:
    current = [poi["id"] for poi in route]
    return any(current == [poi["id"] for poi in existing] for existing in existing_routes)


def _is_same_stop_set(route: list[dict], existing_routes: list[list[dict]]) -> bool:
    current = {poi["id"] for poi in route}
    return any(current == {poi["id"] for poi in existing} for existing in existing_routes)


def _rotate_route_order(route: list[dict], shift: int) -> list[dict]:
    if len(route) <= 2:
        return route
    shift = shift % len(route)
    return route[shift:] + route[:shift] if shift else route


def _clean_route(route: list[dict]) -> list[dict]:
    cleaned = []
    for poi in route:
        cleaned.append({k: v for k, v in poi.items() if not k.startswith("_")})
    return cleaned
