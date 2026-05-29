import json
import math
from itertools import permutations
from db.database import execute_query, execute_one, execute_write


def haversine_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """计算两点之间的距离（米）"""
    R = 6371000  # 地球半径（米）
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def score_poi(poi: dict, constraints: dict, user_profile: dict = None, area_center: tuple = None) -> float:
    """
    POI 打分公式
    poi_score = 0.25 * preference_match
              + 0.20 * rating_score
              + 0.15 * cost_fit
              + 0.15 * distance_fit
              + 0.10 * ugc_hot_score
              + 0.10 * queue_fit
              + 0.05 * opening_fit
    """
    score = 0.0

    # 1. 偏好匹配 (0-1)
    preferences = constraints.get("preferences", [])
    poi_tags = json.loads(poi.get("tags", "[]")) if isinstance(poi.get("tags"), str) else poi.get("tags", [])
    poi_category = poi.get("category", "")

    preference_match = 0.0
    if preferences:
        match_count = sum(1 for p in preferences if p in poi_tags or p in poi_category)
        preference_match = min(match_count / len(preferences), 1.0)
    else:
        preference_match = 0.5  # 无偏好时给默认分
    score += 0.25 * preference_match

    # 2. 评分 (0-1)
    rating = poi.get("rating", 0)
    rating_score = rating / 5.0 if rating else 0.5
    score += 0.20 * rating_score

    # 3. 预算匹配 (0-1)
    budget = constraints.get("budget")
    avg_cost = poi.get("avg_cost", 0)
    if budget and avg_cost:
        if avg_cost <= budget * 0.3:
            cost_fit = 1.0
        elif avg_cost <= budget * 0.5:
            cost_fit = 0.8
        elif avg_cost <= budget:
            cost_fit = 0.5
        else:
            cost_fit = 0.2
    else:
        cost_fit = 0.5
    score += 0.15 * cost_fit

    # 4. 距离适配 (0-1) - 根据与区域中心的距离计算
    if area_center:
        dist = haversine_distance(poi["lng"], poi["lat"], area_center[0], area_center[1])
        # 指数衰减：近距离 POI 得分显著更高，distance_weight_boost 越大衰减越快
        boost = constraints.get("distance_weight_boost", 1.0)
        decay = 2000 * boost  # boost=1 时 2km 衰减到 0.37，boost=3 时 667m 就衰减到 0.37
        distance_fit = math.exp(-dist / decay)
    else:
        distance_fit = 0.5
    # distance_weight_boost: 少走路时动态提高距离权重
    dist_weight = 0.15 * constraints.get("distance_weight_boost", 1.0)
    score += dist_weight * distance_fit

    # 5. UGC 热度 (0-1)
    review = poi.get("review", {})
    sentiment = review.get("sentiment", 0)
    keywords = review.get("keywords", [])
    ugc_hot_score = 0.5
    if sentiment > 0:
        ugc_hot_score = 0.5 + sentiment * 0.5
    if any(kw in ["推荐", "必去", "打卡"] for kw in keywords):
        ugc_hot_score = min(ugc_hot_score + 0.2, 1.0)
    score += 0.10 * ugc_hot_score

    # 6. 排队匹配 (0-1)
    queue_tolerance = constraints.get("queue_tolerance", 2)  # 1=低, 2=中, 3=高
    queue_hint = review.get("queue_hint", "unknown")
    queue_fit = 0.5
    if queue_hint == "low":
        queue_fit = 1.0
    elif queue_hint == "medium":
        queue_fit = 0.7 if queue_tolerance >= 2 else 0.4
    elif queue_hint == "high":
        queue_fit = 0.8 if queue_tolerance >= 3 else 0.3
    score += 0.10 * queue_fit

    # 7. 营业时间匹配 (0-1) - 第一版没有营业时间数据，默认 0.5
    opening_fit = 0.5
    score += 0.05 * opening_fit

    return round(score, 4)


def build_route_matrix(pois: list[dict], mode: str = "walking") -> dict:
    """
    构建路线矩阵
    返回: {(poi_id_1, poi_id_2): {"distance_m": int, "duration_s": int}}
    """
    matrix = {}

    for i, poi_a in enumerate(pois):
        for j, poi_b in enumerate(pois):
            if i >= j:
                continue

            key = (poi_a["id"], poi_b["id"])

            # 先查缓存
            cached = execute_one(
                "SELECT distance_m, duration_s FROM route_cache WHERE origin_poi_id = ? AND dest_poi_id = ? AND mode = ?",
                (poi_a["id"], poi_b["id"], mode)
            )

            if cached:
                matrix[key] = {
                    "distance_m": cached["distance_m"],
                    "duration_s": cached["duration_s"],
                }
                # 反向也缓存
                matrix[(poi_b["id"], poi_a["id"])] = {
                    "distance_m": cached["distance_m"],
                    "duration_s": cached["duration_s"],
                }
            else:
                # 用直线距离估算
                dist = haversine_distance(poi_a["lng"], poi_a["lat"], poi_b["lng"], poi_b["lat"])

                # 根据出行方式估算时间
                speed_map = {
                    "walking": 1.2,  # 米/秒
                    "bicycling": 4.0,
                    "driving": 10.0,
                }
                speed = speed_map.get(mode, 1.2)
                duration = int(dist / speed)

                matrix[key] = {
                    "distance_m": int(dist),
                    "duration_s": duration,
                }
                matrix[(poi_b["id"], poi_a["id"])] = {
                    "distance_m": int(dist),
                    "duration_s": duration,
                }

                # 保存到缓存
                execute_write("""
                    INSERT OR REPLACE INTO route_cache (origin_poi_id, dest_poi_id, mode, distance_m, duration_s)
                    VALUES (?, ?, ?, ?, ?)
                """, (poi_a["id"], poi_b["id"], mode, int(dist), duration))

    return matrix


def calculate_route_score(route: list[dict], matrix: dict, constraints: dict) -> dict:
    """计算一条路线的总分"""
    total_poi_score = 0
    total_distance = 0
    total_duration = 0
    total_cost = 0

    for i, poi in enumerate(route):
        total_poi_score += poi.get("_score", 0)
        total_cost += poi.get("avg_cost", 0)

        if i > 0:
            prev_id = route[i - 1]["id"]
            curr_id = poi["id"]
            key = (prev_id, curr_id)
            if key in matrix:
                total_distance += matrix[key]["distance_m"]
                total_duration += matrix[key]["duration_s"]

    # 添加每个 POI 的游玩时间（默认 60 分钟）
    play_time = len(route) * 60 * 60
    total_duration += play_time

    # 路线总分（距离惩罚受 distance_weight_boost 影响）
    dist_boost = constraints.get("distance_weight_boost", 1.0)
    # 距离惩罚用平方项，让长距离路线受到更重惩罚
    route_score = (
        total_poi_score
        - 0.0000005 * (total_distance ** 2) * dist_boost
        - 0.01 * (total_duration / 60)
    )

    # 预算惩罚
    budget = constraints.get("budget")
    if budget and total_cost > budget:
        route_score -= (total_cost - budget) * 0.1

    return {
        "route_score": round(route_score, 2),
        "total_poi_score": round(total_poi_score, 2),
        "total_distance_m": total_distance,
        "total_duration_s": total_duration,
        "total_cost": total_cost,
    }


def optimize_route(pois: list[dict], constraints: dict, max_stops: int = 5,
                   area_center: tuple = None) -> dict:
    """
    路线枚举优化
    输出 Top 3 方案：综合最优、少走路、省钱
    返回: {"plans": [...], "matrix": {...}}
    """
    if len(pois) <= 1:
        return {"plans": [{"name": "综合最优", "route": pois, "score": {}}], "matrix": {}}

    # 解析 area_center：可能是字符串 "lng,lat" 或元组 (lng, lat)
    center = None
    if area_center:
        if isinstance(area_center, str) and "," in area_center:
            parts = area_center.split(",")
            center = (float(parts[0]), float(parts[1]))
        elif isinstance(area_center, (list, tuple)) and len(area_center) == 2:
            center = (float(area_center[0]), float(area_center[1]))

    # 为每个 POI 打分（传入 area_center 计算 distance_fit）
    for poi in pois:
        poi["_score"] = score_poi(poi, constraints, area_center=center)

    # 类型分桶：按 category 分桶，每桶取 Top 3，确保路线多样性
    candidates = _bucket_and_select(pois, max_stops)

    # 构建路线矩阵
    matrix = build_route_matrix(candidates, constraints.get("transport_mode", "walking"))

    # 枚举所有排列（限制数量避免组合爆炸）
    all_routes = []
    perm_limit = min(len(candidates), max_stops)

    for perm in permutations(candidates, perm_limit):
        route = list(perm)
        score_info = calculate_route_score(route, matrix, constraints)
        all_routes.append({
            "route": route,
            "score_info": score_info,
        })

    if not all_routes:
        return {"plans": [], "matrix": matrix}

    # 时间约束过滤：丢弃超时方案
    duration_limit = constraints.get("duration_minutes")
    if duration_limit:
        time_limit_s = duration_limit * 60
        filtered = [r for r in all_routes if r["score_info"]["total_duration_s"] <= time_limit_s]
        if filtered:
            all_routes = filtered

    # 排序生成不同方案
    results = []

    def _route_key(route):
        return tuple(p["id"] for p in route)

    def _is_duplicate(route):
        key = _route_key(route)
        return any(_route_key(r["route"]) == key for r in results)

    # 1. 综合最优
    all_routes.sort(key=lambda x: x["score_info"]["route_score"], reverse=True)
    best = all_routes[0]
    results.append({
        "name": "综合最优",
        "route": _clean_route(best["route"]),
        "score": best["score_info"],
    })

    # 2. 少走路
    all_routes.sort(key=lambda x: x["score_info"]["total_distance_m"])
    for r in all_routes:
        if not _is_duplicate(r["route"]):
            results.append({
                "name": "少走路",
                "route": _clean_route(r["route"]),
                "score": r["score_info"],
            })
            break

    # 3. 省钱
    all_routes.sort(key=lambda x: x["score_info"]["total_cost"])
    for r in all_routes:
        if not _is_duplicate(r["route"]):
            results.append({
                "name": "省钱",
                "route": _clean_route(r["route"]),
                "score": r["score_info"],
            })
            break

    # 如果不足 3 个方案，从剩余中补充
    while len(results) < 3 and len(results) < len(all_routes):
        all_routes.sort(key=lambda x: x["score_info"]["route_score"], reverse=True)
        for r in all_routes:
            if not _is_duplicate(r["route"]):
                results.append({
                    "name": f"方案{len(results) + 1}",
                    "route": _clean_route(r["route"]),
                    "score": r["score_info"],
                })
                break
        else:
            break

    return {"plans": results, "matrix": matrix}


def _bucket_and_select(pois: list[dict], max_stops: int) -> list[dict]:
    """按类型分桶，每桶取 Top N，确保路线包含多种类型"""
    buckets = {}
    for poi in pois:
        cat = poi.get("category", "其他")
        buckets.setdefault(cat, []).append(poi)

    # 每桶按 _score 排序取 Top 3
    per_bucket = max(2, max_stops // max(len(buckets), 1))
    selected = []
    for cat, bucket_pois in buckets.items():
        bucket_pois.sort(key=lambda x: x.get("_score", 0), reverse=True)
        selected.extend(bucket_pois[:per_bucket])

    # 如果候选不足 max_stops，直接返回
    if len(selected) <= max_stops:
        return selected

    # 否则全局按 _score 排序取 Top max_stops
    selected.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return selected[:max_stops + 2]  # 多取 2 个给排列更多选择


def _clean_route(route: list[dict]) -> list[dict]:
    """清理路线数据，移除内部字段"""
    cleaned = []
    for poi in route:
        clean_poi = {k: v for k, v in poi.items() if not k.startswith("_")}
        cleaned.append(clean_poi)
    return cleaned
