import json
import math
from itertools import permutations
from db.database import execute_one, execute_write


CATEGORY_DEFAULT_COST = {
    "咖啡": 40,
    "餐厅": 110,
    "甜品": 35,
    "购物": 180,
    "夜景": 120,
    "景点": 40,
    "展览": 50,
    "公园": 0,
    "娱乐": 120,
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


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _effective_unit_cost(poi: dict) -> float:
    cost = _to_float(poi.get("avg_cost"), 0)
    if cost > 0:
        return cost
    category = poi.get("category", "")
    tags = _safe_tags(poi)
    if "免费" in tags:
        return 0
    return CATEGORY_DEFAULT_COST.get(category, 30)


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

    preference_match = _preference_match_score(poi, preferences)
    score += 0.38 * preference_match

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
    if any(kw in ["推荐", "必去", "打卡", "本地人推荐"] for kw in keywords + _safe_tags(poi)):
        hot_score += 0.12
    score += 0.10 * min(hot_score, 1.0)

    queue_tolerance = constraints.get("queue_tolerance", 2)
    tags = _safe_tags(poi)
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
                total_distance += matrix[key]["distance_m"]
                total_duration += matrix[key]["duration_s"]

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
    )

    budget = constraints.get("budget")
    if budget:
        if total_cost > budget:
            route_score -= (total_cost - budget) * 0.08
        else:
            utilization = total_cost / budget
            # 不鼓励“花得越少越好”的伪最优，60%-85% 预算利用更符合游玩规划。
            route_score += max(0, 0.55 - abs(utilization - 0.72)) * 1.8

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

    center = _parse_center(area_center)
    for poi in pois:
        poi["_score"] = score_poi(poi, constraints, area_center=center)

    trip_days = max(1, int(constraints.get("trip_days") or 1))
    if trip_days > 1:
        return _optimize_multiday_route(pois, constraints, trip_days, area_center=center)

    hard_limit = 8 if max_stops <= 7 else 9
    candidates = _bucket_and_select(pois, max_stops=max_stops, hard_limit=hard_limit)
    matrix = build_route_matrix(candidates, constraints.get("transport_mode", "walking"))
    route_len = min(len(candidates), max_stops)
    duration_limit = constraints.get("duration_minutes")
    if duration_limit:
        route_len = min(route_len, max(4, duration_limit // 75))
    if route_len == 0:
        return {"plans": [], "matrix": matrix}

    all_routes = []
    for perm in permutations(candidates, route_len):
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
    if budget:
        budget_fit = [r for r in all_routes if r["score_info"]["total_cost"] <= budget * 1.05]
        if budget_fit:
            all_routes = budget_fit

    results = []

    def add_plan(name: str, style: str, route_item: dict, highlights: list[str], allow_similar: bool = False):
        display_route = _order_route_for_day_flow(route_item["route"], matrix)
        display_route = _trim_route_to_budget(display_route, constraints)
        if _is_same_order(display_route, [r["route"] for r in results]):
            display_route = _make_route_distinct(display_route, candidates, [r["route"] for r in results], style)
        display_score = calculate_route_score(display_route, matrix, constraints)
        if _is_same_order(display_route, [r["route"] for r in results]):
            return
        if not allow_similar and _is_too_similar(display_route, [r["route"] for r in results]):
            return
        results.append({
            "name": name,
            "style": style,
            "route": _clean_route(display_route),
            "score": display_score,
            "highlights": highlights,
        })

    best = max(all_routes, key=lambda x: x["score_info"]["route_score"])
    add_plan("综合推荐", "balanced", best, ["偏好匹配", "预算利用适中", "类型丰富"])

    walking = _route_item_from_direct_selection(
        _direct_style_route(candidates, route_len, "short_walk"),
        matrix,
        constraints,
    ) or min(
        all_routes,
        key=lambda x: (x["score_info"]["total_distance_m"], -x["score_info"]["route_score"]),
    )
    add_plan("少走路", "short_walk", walking, ["地点更集中", "步行距离更短"], allow_similar=True)

    food_fun = _route_item_from_direct_selection(
        _direct_style_route(candidates, route_len, "food_fun"),
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
    add_plan("吃好玩好", "food_fun", food_fun, ["餐饮和消费体验更完整", "适合逛吃"], allow_similar=True)

    low_budget = _route_item_from_direct_selection(
        _direct_style_route(candidates, route_len, "budget"),
        matrix,
        constraints,
    ) or min(
        all_routes,
        key=lambda x: (x["score_info"]["total_cost"], x["score_info"]["total_distance_m"], -x["score_info"]["route_score"]),
    )
    add_plan("省钱轻量", "budget", low_budget, ["低消费", "保留核心体验"], allow_similar=True)

    # 如果风格方案因相似度被过滤，补充差异最大的高分路线。
    sorted_routes = sorted(all_routes, key=lambda x: x["score_info"]["route_score"], reverse=True)
    for item in sorted_routes:
        if len(results) >= 4:
            break
        add_plan(f"备选方案{len(results) + 1}", "alternative", item, ["补充选择"])

    return {"plans": results, "matrix": matrix}


def _route_item_from_direct_selection(route: list[dict], matrix: dict, constraints: dict) -> dict | None:
    if len(route) < 2:
        return None
    return {"route": route, "score_info": calculate_route_score(route, matrix, constraints)}


def _trim_route_to_budget(route: list[dict], constraints: dict) -> list[dict]:
    budget = constraints.get("budget")
    if not budget:
        return route
    people_count = max(1, int(constraints.get("people_count") or 1))
    min_stops = 5 if (constraints.get("duration_minutes") or 0) >= 420 else 4
    trimmed = list(route)

    def total_cost(items: list[dict]) -> float:
        return sum(_effective_unit_cost(poi) * people_count for poi in items)

    while total_cost(trimmed) > budget * 1.05 and len(trimmed) > min_stops:
        removable = max(
            trimmed,
            key=lambda p: (
                _effective_unit_cost(p) * people_count,
                1 if p.get("category") == "餐厅" else 0,
                -p.get("_score", 0),
            ),
        )
        trimmed.remove(removable)
    return trimmed


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
            if not _is_same_order(candidate_route, existing_routes):
                return candidate_route
    return route


def _direct_style_route(candidates: list[dict], target_len: int, style: str) -> list[dict]:
    if not candidates or target_len <= 0:
        return []

    selected: list[dict] = []
    seen: set[str] = set()

    def add_from(category: str, count: int = 1, reverse_cost: bool = False):
        bucket = [p for p in candidates if p.get("category") == category and p["id"] not in seen]
        if style == "budget":
            bucket.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
        elif reverse_cost:
            bucket.sort(key=lambda p: (_effective_unit_cost(p), p.get("_score", 0)), reverse=True)
        else:
            bucket.sort(key=lambda p: p.get("_score", 0), reverse=True)
        for poi in bucket[:count]:
            if len(selected) >= target_len:
                return
            selected.append(poi)
            seen.add(poi["id"])

    if style == "food_fun":
        for category, count in [("餐厅", 2), ("甜品", 1), ("咖啡", 1), ("购物", 1), ("娱乐", 1), ("夜景", 1), ("景点", 1), ("展览", 1)]:
            add_from(category, count, reverse_cost=category in {"餐厅", "购物", "娱乐"})
    elif style == "budget":
        for category in ["公园", "展览", "景点", "咖啡", "甜品", "餐厅", "购物", "娱乐", "夜景"]:
            add_from(category)
    elif style == "short_walk":
        ordered = _order_route_nearest(candidates, build_route_matrix(candidates[: min(len(candidates), 10)]))
        for poi in ordered:
            if poi["id"] not in seen and len(selected) < target_len:
                selected.append(poi)
                seen.add(poi["id"])

    remaining = [p for p in candidates if p["id"] not in seen]
    remaining.sort(key=lambda p: p.get("_score", 0), reverse=True)
    selected.extend(remaining[: max(0, target_len - len(selected))])
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
    target_stops = min(len(pois), max(6, min(trip_days * 4, 24)))
    candidates = _bucket_and_select(pois, max_stops=target_stops, hard_limit=min(max(target_stops + 6, 12), 30))
    matrix = build_route_matrix(candidates, constraints.get("transport_mode", "walking"))
    start_center = _parse_center(constraints.get("start_location")) or area_center

    routes = []
    selected_balanced = _select_candidates_by_style(candidates, constraints, target_stops, "balanced")
    routes.append(("多日综合", "balanced", selected_balanced, ["按天拆分", "类型均衡", "转场顺序优化"]))

    selected_premium = _select_candidates_by_style(candidates, constraints, target_stops, "premium")
    routes.append(("预算充分", "premium", selected_premium, ["提高预算利用", "更多餐饮与体验消费", "适合不想太省"]))

    selected_compact = _select_candidates_by_style(candidates, constraints, max(5, target_stops - trip_days), "compact")
    routes.append(("少折返", "compact", selected_compact, ["减少跨城折返", "每天集中片区"]))

    selected_light = _select_candidates_by_style(candidates, constraints, max(5, target_stops - trip_days), "light")
    routes.append(("轻松留白", "relaxed", selected_light, ["每天不过载", "留出临时活动和休息时间"]))

    results = []
    for name, style, route, highlights in routes:
        ordered = _order_route_nearest(_dedupe_route(route), matrix, start_center)
        if len(ordered) < 3:
            continue
        score_info = calculate_route_score(ordered, matrix, constraints)
        if _is_same_order(ordered, [r["route"] for r in results]):
            continue
        results.append({
            "name": name,
            "style": style,
            "route": _clean_route(ordered),
            "score": score_info,
            "highlights": highlights,
        })

    if not results:
        ordered = _order_route_nearest(candidates[:target_stops], matrix, start_center)
        results.append({
            "name": "多日综合",
            "style": "balanced",
            "route": _clean_route(ordered),
            "score": calculate_route_score(ordered, matrix, constraints),
            "highlights": ["按天拆分"],
        })

    return {"plans": results[:4], "matrix": matrix}


def _select_candidates_by_style(candidates: list[dict], constraints: dict, target_stops: int, style: str) -> list[dict]:
    people_count = max(1, int(constraints.get("people_count") or 1))
    budget = constraints.get("budget") or 0
    trip_days = max(1, int(constraints.get("trip_days") or 1))
    target_cost = budget * (0.90 if style == "premium" else 0.78 if style == "balanced" else 0.48)
    persona_order = (constraints.get("persona_strategy") or {}).get("category_order") or []
    categories_order = list(dict.fromkeys(persona_order + ["景点", "餐厅", "咖啡", "展览", "购物", "公园", "甜品", "娱乐", "夜景"]))
    buckets: dict[str, list[dict]] = {}
    for poi in candidates:
        buckets.setdefault(poi.get("category", "其他"), []).append(poi)

    for category, bucket in buckets.items():
        if style == "premium":
            bucket.sort(key=lambda p: (_effective_unit_cost(p), p.get("_score", 0)), reverse=True)
        elif style == "light":
            bucket.sort(key=lambda p: (_effective_unit_cost(p), -p.get("_score", 0)))
        else:
            bucket.sort(key=lambda p: p.get("_score", 0), reverse=True)

    selected = []
    seen = set()
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
        remaining.sort(key=lambda p: (_effective_unit_cost(p), p.get("_score", 0)), reverse=True)
        for poi in remaining:
            if len(selected) >= target_stops:
                break
            if current_cost < target_cost or poi.get("category") in {"餐厅", "购物", "夜景"}:
                selected.append(poi)
                current_cost += _effective_unit_cost(poi) * people_count
    else:
        remaining.sort(key=lambda p: p.get("_score", 0), reverse=True)
        selected.extend(remaining[: max(0, target_stops - len(selected))])

    selected = selected[:target_stops]
    if budget:
        cap_ratio = {
            "premium": 1.04,
            "balanced": 0.98,
            "compact": 0.86,
            "light": 0.68,
        }.get(style, 0.98)
        min_stops = min(target_stops, max(5, trip_days * (3 if style in {"balanced", "premium"} else 2)))
        selected = _fit_route_to_budget(selected, candidates, people_count, budget * cap_ratio, min_stops, target_stops)
        if style == "premium":
            selected = _raise_budget_use(selected, candidates, people_count, budget * 0.92, budget * cap_ratio, target_stops)

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

    while route_cost(selected) > budget_cap and len(selected) > min_stops:
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
        if len(selected) < min_stops or next_cost <= budget_cap:
            selected.append(poi)
            selected_ids.add(poi["id"])

    return selected


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
    remaining.sort(key=lambda p: (_effective_unit_cost(p), p.get("_score", 0)), reverse=True)

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

    if category == "餐厅":
        if any(word in text for word in ["早茶", "早餐", "brunch", "茶点"]):
            return 1
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
    if category == "夜景":
        return 7
    return 8


def _dedupe_route(route: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for poi in route:
        if poi["id"] in seen:
            continue
        result.append(poi)
        seen.add(poi["id"])
    return result


def _bucket_and_select(pois: list[dict], max_stops: int, hard_limit: int = 8) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for poi in pois:
        buckets.setdefault(poi.get("category", "其他"), []).append(poi)

    for bucket in buckets.values():
        bucket.sort(key=lambda x: x.get("_score", 0), reverse=True)

    selected = []
    preferred_order = ["餐厅", "咖啡", "购物", "景点", "展览", "公园", "甜品", "娱乐", "夜景"]
    for category in preferred_order:
        if category in buckets and buckets[category]:
            selected.append(buckets[category].pop(0))

    remaining = [poi for bucket in buckets.values() for poi in bucket]
    remaining.sort(key=lambda x: x.get("_score", 0), reverse=True)
    selected.extend(remaining)

    deduped = []
    seen = set()
    for poi in selected:
        if poi["id"] in seen:
            continue
        deduped.append(poi)
        seen.add(poi["id"])
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
        if overlap >= 0.8:
            return True
    return False


def _is_same_order(route: list[dict], existing_routes: list[list[dict]]) -> bool:
    current = [poi["id"] for poi in route]
    return any(current == [poi["id"] for poi in existing] for existing in existing_routes)


def _clean_route(route: list[dict]) -> list[dict]:
    cleaned = []
    for poi in route:
        cleaned.append({k: v for k, v in poi.items() if not k.startswith("_")})
    return cleaned
