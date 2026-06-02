import json
import math
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from db.database import execute_query, execute_one, execute_write
from tools.amap import search_nearby, search_poi


PREFERENCE_KEYWORDS = {
    "探店": ["咖啡店", "特色小店", "甜品"],
    "看展": ["美术馆", "博物馆", "展览"],
    "美食": ["老字号粤菜", "广式早茶", "酒家", "高分餐厅", "餐厅", "本地菜", "小吃"],
    "亲子": ["公园", "亲子乐园", "博物馆"],
    "夜景": ["夜景", "酒吧", "Livehouse", "演出", "观景台"],
    "咖啡": ["咖啡店", "咖啡馆"],
    "购物": ["购物中心", "商场", "步行街", "买手店"],
    "自然": ["公园", "景区", "湖"],
    "爬山": ["登山步道", "森林公园", "山", "风景区"],
    "户外": ["森林公园", "露营地", "徒步", "骑行公园"],
    "运动": ["运动馆", "攀岩馆", "骑行", "篮球馆"],
    "娱乐": ["演出", "Livehouse", "市集", "剧场", "娱乐", "游乐"],
    "游戏": ["电竞馆", "电玩", "密室逃脱", "剧本杀", "桌游吧", "网咖"],
    "热闹": ["商圈", "步行街", "夜景"],
    "拍照": ["景点", "美术馆", "网红打卡"],
    "历史": ["博物馆", "老街", "历史文化"],
    "少排队": ["公园", "博物馆", "本地餐厅"],
}

PREFERENCE_CATEGORIES = {
    "美食": ["餐厅", "甜品"],
    "咖啡": ["咖啡"],
    "探店": ["咖啡", "甜品", "购物"],
    "看展": ["展览"],
    "自然": ["公园", "景点"],
    "爬山": ["公园", "景点"],
    "户外": ["公园", "景点"],
    "运动": ["娱乐", "公园"],
    "娱乐": ["娱乐", "夜景", "购物"],
    "游戏": ["娱乐", "购物"],
    "购物": ["购物"],
    "亲子": ["公园", "展览", "景点"],
    "夜景": ["夜景", "景点"],
    "热闹": ["购物", "夜景", "餐厅"],
    "拍照": ["景点", "展览", "咖啡"],
    "历史": ["展览", "景点"],
    "少排队": ["公园", "展览", "景点"],
}

FALLBACK_CITY_POIS = {
    "上海": [
        {"name": "南京路步行街", "address": "上海市黄浦区南京东路", "lng": 121.4846, "lat": 31.2363, "category": "购物", "tags": ["步行街", "商圈", "热闹", "逛街"], "rating": 4.5, "avg_cost": 120},
        {"name": "外滩", "address": "上海市黄浦区中山东一路", "lng": 121.4903, "lat": 31.2397, "category": "景点", "tags": ["夜景", "地标", "拍照", "免费"], "rating": 4.8, "avg_cost": 0},
        {"name": "豫园商城", "address": "上海市黄浦区福佑路168号", "lng": 121.4921, "lat": 31.2272, "category": "购物", "tags": ["小吃", "老街", "热闹", "本地特色"], "rating": 4.4, "avg_cost": 100},
        {"name": "新天地", "address": "上海市黄浦区太仓路181弄", "lng": 121.4752, "lat": 31.2197, "category": "夜景", "tags": ["商圈", "酒吧", "夜景", "热闹"], "rating": 4.6, "avg_cost": 180},
        {"name": "上海博物馆", "address": "上海市黄浦区人民大道201号", "lng": 121.4755, "lat": 31.2303, "category": "展览", "tags": ["博物馆", "文化", "免费", "历史"], "rating": 4.7, "avg_cost": 0},
        {"name": "田子坊", "address": "上海市黄浦区泰康路210弄", "lng": 121.4687, "lat": 31.2107, "category": "景点", "tags": ["文艺", "小店", "拍照", "热闹"], "rating": 4.2, "avg_cost": 80},
        {"name": "老吉士酒家(天平路店)", "address": "上海市徐汇区天平路41号", "lng": 121.4415, "lat": 31.2046, "category": "餐厅", "tags": ["本帮菜", "老字号", "聚餐"], "rating": 4.4, "avg_cost": 180},
        {"name": "Manner Coffee(淮海中路店)", "address": "上海市黄浦区淮海中路", "lng": 121.4689, "lat": 31.2224, "category": "咖啡", "tags": ["咖啡", "平价", "商圈"], "rating": 4.5, "avg_cost": 30},
        {"name": "哈尔滨食品厂", "address": "上海市黄浦区淮海中路603号", "lng": 121.4683, "lat": 31.2228, "category": "甜品", "tags": ["老字号", "甜品", "点心"], "rating": 4.3, "avg_cost": 35},
        {"name": "复兴公园", "address": "上海市黄浦区雁荡路105号", "lng": 121.4692, "lat": 31.2160, "category": "公园", "tags": ["公园", "散步", "免费", "轻松"], "rating": 4.4, "avg_cost": 0},
    ],
    "广州": [
        {"name": "北京路步行街", "address": "广州市越秀区北京路", "lng": 113.2708, "lat": 23.1259, "category": "购物", "tags": ["步行街", "商圈", "小吃", "热闹"], "rating": 4.5, "avg_cost": 100},
        {"name": "永庆坊", "address": "广州市荔湾区恩宁路99号", "lng": 113.2481, "lat": 23.1148, "category": "景点", "tags": ["老街", "文创", "拍照", "历史"], "rating": 4.6, "avg_cost": 60},
        {"name": "沙面岛", "address": "广州市荔湾区沙面南街", "lng": 113.2391, "lat": 23.1105, "category": "景点", "tags": ["建筑", "散步", "拍照", "免费"], "rating": 4.7, "avg_cost": 0},
        {"name": "陶陶居(第十甫路总店)", "address": "广州市荔湾区第十甫路20号", "lng": 113.2515, "lat": 23.1170, "category": "餐厅", "tags": ["早茶", "粤菜", "老字号", "排队"], "rating": 4.4, "avg_cost": 120},
        {"name": "点都德(德粤楼店)", "address": "广州市越秀区中山四路", "lng": 113.2727, "lat": 23.1262, "category": "餐厅", "tags": ["早茶", "粤菜", "适合聚餐"], "rating": 4.5, "avg_cost": 110},
        {"name": "广东省博物馆", "address": "广州市天河区珠江东路2号", "lng": 113.3207, "lat": 23.1163, "category": "展览", "tags": ["博物馆", "免费", "亲子", "文化"], "rating": 4.7, "avg_cost": 0},
        {"name": "花城广场", "address": "广州市天河区珠江新城", "lng": 113.3246, "lat": 23.1198, "category": "夜景", "tags": ["夜景", "地标", "免费", "热闹"], "rating": 4.6, "avg_cost": 0},
        {"name": "广州塔", "address": "广州市海珠区阅江西路222号", "lng": 113.3307, "lat": 23.1055, "category": "景点", "tags": ["地标", "夜景", "拍照"], "rating": 4.5, "avg_cost": 150},
        {"name": "Tims咖啡(北京路店)", "address": "广州市越秀区北京路", "lng": 113.2702, "lat": 23.1265, "category": "咖啡", "tags": ["咖啡", "商圈", "休息"], "rating": 4.2, "avg_cost": 35},
        {"name": "南信牛奶甜品专家", "address": "广州市荔湾区第十甫路47号", "lng": 113.2510, "lat": 23.1173, "category": "甜品", "tags": ["甜品", "老字号", "双皮奶"], "rating": 4.3, "avg_cost": 28},
    ],
}


def _normalize_city(city: str | None) -> str:
    city_clean = (city or "杭州").strip()
    if city_clean.endswith("市") and len(city_clean) > 2:
        city_clean = city_clean[:-1]
    if city_clean.endswith("城区") and len(city_clean) > 3:
        city_clean = city_clean[:-2]
    for known in ["杭州", "北京", "上海", "广州", "深圳", "成都", "南京", "苏州", "重庆", "武汉", "西安", "厦门"]:
        if known in city_clean:
            return known
    return city_clean or "杭州"


def _ensure_fallback_city_pois(city: str) -> None:
    city = _normalize_city(city)
    pois = FALLBACK_CITY_POIS.get(city)
    if not pois:
        return

    for poi in pois:
        existing = execute_one(
            "SELECT id FROM poi WHERE city = ? AND name = ?",
            (city, poi["name"]),
        )
        if existing:
            continue
        poi_id = f"fallback_{uuid.uuid5(uuid.NAMESPACE_DNS, city + ':' + poi['name']).hex[:12]}"
        address = poi.get("address", "")
        if isinstance(address, list):
            address = " ".join(str(item) for item in address if item)
        execute_write(
            """
            INSERT INTO poi (id, source, source_id, name, city, adcode, address, lng, lat, category, tags, rating, avg_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                poi_id,
                "fallback",
                None,
                poi["name"],
                city,
                "",
                poi["address"],
                poi["lng"],
                poi["lat"],
                poi["category"],
                json.dumps(poi["tags"], ensure_ascii=False),
                poi["rating"],
                poi["avg_cost"],
            ),
        )


def get_poi_by_id(poi_id: str) -> dict | None:
    return execute_one("SELECT * FROM poi WHERE id = ?", (poi_id,))


def search_local_pois(
    city: str = None,
    category: str = None,
    tags: list[str] = None,
    max_cost: float = None,
    limit: int = 20,
) -> list[dict]:
    conditions = []
    params = []

    if city:
        conditions.append("city = ?")
        params.append(_normalize_city(city))

    if category:
        conditions.append("category = ?")
        params.append(category)

    if max_cost is not None:
        conditions.append("(avg_cost <= ? OR avg_cost = 0)")
        params.append(max_cost)

    if tags:
        tag_conditions = []
        for tag in tags:
            tag_conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")
        conditions.append("(" + " OR ".join(tag_conditions) + ")")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
    SELECT * FROM poi
    WHERE {where_clause}
    ORDER BY rating DESC, popularity DESC, avg_cost ASC
    LIMIT ?
    """
    params.append(limit)
    return execute_query(sql, tuple(params))


def search_pois_by_preferences(
    city: str,
    preferences: list[str],
    max_cost: float = None,
    limit: int = 15,
) -> list[dict]:
    city = _normalize_city(city)
    _ensure_fallback_city_pois(city)

    categories = []
    for pref in preferences or []:
        categories.extend(PREFERENCE_CATEGORIES.get(pref, []))
    categories = list(dict.fromkeys(categories))

    if not categories:
        return search_local_pois(city=city, max_cost=max_cost, limit=limit)

    all_pois = []
    seen_ids = set()
    per_category_limit = max(3, limit // max(len(categories), 1) + 1)
    for category in categories:
        pois = search_local_pois(city=city, category=category, max_cost=max_cost, limit=per_category_limit)
        for poi in pois:
            if poi["id"] not in seen_ids:
                all_pois.append(poi)
                seen_ids.add(poi["id"])

    # 偏好过滤过严时，用同城高分 POI 补足，保证可生成多元路线。
    if len(all_pois) < min(6, limit):
        for poi in search_local_pois(city=city, max_cost=max_cost, limit=limit):
            if poi["id"] not in seen_ids:
                all_pois.append(poi)
                seen_ids.add(poi["id"])
            if len(all_pois) >= limit:
                break

    return all_pois[:limit]


def fetch_and_save_pois_from_amap(keyword: str, city: str, limit: int = 5) -> list[dict]:
    city_clean = _normalize_city(city)
    pois_data = _amap_search_with_fallback(keyword, city_clean)
    return _save_amap_pois(pois_data, keyword, city_clean, limit)


def _save_amap_pois(pois_data: list[dict], keyword: str, city_clean: str, limit: int = 5) -> list[dict]:
    saved_pois = []
    for poi in pois_data[:limit]:
        if _is_noise_poi(poi):
            continue
        location = poi.get("location")
        if not location or "," not in location:
            continue
        lng, lat = location.split(",", 1)
        existing = execute_one(
            "SELECT id FROM poi WHERE name = ? AND city = ?",
            (poi["name"], city_clean),
        )
        if existing:
            existing_poi = get_poi_by_id(existing["id"])
            if existing_poi:
                inferred = _infer_category(poi.get("type", ""), keyword)
                if inferred in {"咖啡", "展览", "购物", "夜景"} and existing_poi.get("category") != inferred:
                    execute_write("UPDATE poi SET category = ? WHERE id = ?", (inferred, existing["id"]))
                    existing_poi = get_poi_by_id(existing["id"])
                saved_pois.append(existing_poi)
            continue

        poi_id = f"poi_{uuid.uuid4().hex[:8]}"
        category = _infer_category(poi.get("type", ""), keyword)
        try:
            rating = float(poi.get("rating", 0)) if poi.get("rating") else None
        except (TypeError, ValueError):
            rating = None
        try:
            avg_cost = float(poi.get("cost", 0)) if poi.get("cost") else 0
        except (TypeError, ValueError):
            avg_cost = 0

        address = poi.get("address", "")
        if isinstance(address, list):
            address = " ".join(str(item) for item in address if item)

        poi_city = _normalize_city(poi.get("cityname") or city_clean)
        execute_write(
            """
            INSERT INTO poi (id, source, source_id, name, city, adcode, address, lng, lat, category, tags, rating, avg_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                poi_id,
                "amap",
                poi.get("id"),
                poi["name"],
                poi_city,
                poi.get("adcode", ""),
                str(address),
                float(lng),
                float(lat),
                category,
                json.dumps([keyword], ensure_ascii=False),
                rating,
                avg_cost,
            ),
        )
        saved = get_poi_by_id(poi_id)
        if saved:
            saved_pois.append(saved)

    return saved_pois


def search_or_fetch_pois(
    city: str,
    preferences: list[str],
    max_cost: float = None,
    limit: int = 15,
    area: str | None = None,
    adcode: str | None = None,
    center: str | None = None,
    radius_m: int | None = None,
) -> list[dict]:
    city = _normalize_city(city)
    local_pois = search_pois_by_preferences(city, preferences, max_cost, limit)
    local_pois = [poi for poi in local_pois if not _is_noise_poi(poi)]
    local_pois = _filter_pois_by_center(local_pois, center, radius_m or 50000)

    local_categories = {poi.get("category") for poi in local_pois}
    has_visit_category = bool(local_categories & {"景点", "展览", "公园"})
    has_food_or_rest = bool(local_categories & {"餐厅", "甜品", "咖啡"})
    has_experience = bool(local_categories & {"购物", "娱乐", "夜景"})
    if len(local_pois) >= min(8, limit) and len(local_categories) >= 5 and has_visit_category and has_food_or_rest and has_experience:
        return _diversify_pois(_dedupe_pois(local_pois), limit)

    keywords_to_search = _build_search_keywords(preferences, area)

    seen_names = {poi["name"] for poi in local_pois}
    fetched_pois = []
    raw_results: list[tuple[str, list[dict]]] = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(_amap_search_with_fallback, keyword, city, adcode, area, center): keyword
            for keyword in keywords_to_search
        }
        for future in as_completed(future_map):
            keyword = future_map[future]
            try:
                raw_results.append((keyword, future.result()))
            except Exception:
                raw_results.append((keyword, []))

    raw_by_keyword = {keyword: data for keyword, data in raw_results}
    for keyword in keywords_to_search:
        for poi in _save_amap_pois(raw_by_keyword.get(keyword, []), keyword, city, limit=6):
            if poi and poi["name"] not in seen_names:
                fetched_pois.append(poi)
                seen_names.add(poi["name"])

    combined = _filter_pois_by_center(_dedupe_pois(local_pois + fetched_pois), center, radius_m or 50000)

    if len(combined) < min(6, limit):
        _ensure_fallback_city_pois(city)
        combined = _filter_pois_by_center(
            _dedupe_pois(combined + search_local_pois(city=city, max_cost=max_cost, limit=limit)),
            center,
            radius_m or 50000,
        )

    return _diversify_pois(combined, limit)


def _filter_pois_by_center(pois: list[dict], center: str | None, radius_m: int = 50000) -> list[dict]:
    if not center or "," not in center:
        return pois
    try:
        center_lng, center_lat = [float(part) for part in center.split(",", 1)]
    except (TypeError, ValueError):
        return pois

    filtered = []
    for poi in pois:
        try:
            lng = float(poi.get("lng"))
            lat = float(poi.get("lat"))
        except (TypeError, ValueError):
            filtered.append(poi)
            continue
        if _distance_m(lng, lat, center_lng, center_lat) <= radius_m:
            filtered.append(poi)
    return filtered


def _distance_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _build_search_keywords(preferences: list[str] | None, area: str | None = None) -> list[str]:
    keywords = []
    for pref in preferences or []:
        keywords.extend(PREFERENCE_KEYWORDS.get(pref, [pref]))

    # 保证没有偏好或偏好很窄时，也能形成“玩、吃、休息、消费”四类候选。
    core_keywords = ["景点", "餐厅", "咖啡店", "甜品", "商场", "博物馆", "公园", "小吃", "夜市", "娱乐", "演出", "市集"]
    keywords.extend(core_keywords)
    keywords = list(dict.fromkeys(k for k in keywords if k))

    if area:
        area = area.strip()
        area_keywords = [f"{area} {keyword}" for keyword in keywords[:5] if area not in keyword]
        area_keywords.extend([f"{area} {keyword}" for keyword in ["餐厅", "咖啡店", "甜品", "小吃", "商场", "电竞馆", "森林公园", "演出", "市集"]])
        keywords = area_keywords + core_keywords + keywords

    return list(dict.fromkeys(keywords))[:12]


def _amap_search_with_fallback(
    keyword: str,
    city: str,
    adcode: str | None = None,
    area: str | None = None,
    center: str | None = None,
) -> list[dict]:
    if center and "," in center:
        try:
            nearby = json.loads(search_nearby.invoke({"location": center, "keyword": keyword, "radius": 9000}))
            if isinstance(nearby, list) and nearby:
                return nearby
        except Exception:
            pass

    attempts = []
    if adcode:
        attempts.append({"keyword": keyword, "city": adcode})
    attempts.append({"keyword": keyword, "city": city})
    if area and area != city:
        attempts.extend([
            {"keyword": f"{area} {keyword}", "city": adcode or city},
            {"keyword": f"{city} {area} {keyword}", "city": ""},
        ])
    attempts.append({"keyword": f"{city} {keyword}", "city": ""})
    if " " in keyword:
        pure_keyword = keyword.rsplit(" ", 1)[-1]
        attempts.append({"keyword": pure_keyword, "city": city})

    for payload in attempts:
        try:
            result = search_poi.invoke(payload)
            data = json.loads(result)
        except Exception:
            continue
        if isinstance(data, dict) and "error" in data:
            continue
        if isinstance(data, list) and data:
            return data
    return []


def _dedupe_pois(pois: list[dict]) -> list[dict]:
    result = []
    seen_ids = set()
    seen_names = set()
    for poi in pois:
        if not poi or _is_noise_poi(poi):
            continue
        name_key = _normalize_poi_name(poi.get("name", ""))
        if poi.get("id") in seen_ids or name_key in seen_names:
            continue
        result.append(poi)
        seen_ids.add(poi.get("id"))
        seen_names.add(name_key)
    return result


def _normalize_poi_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "").lower())


def _diversify_pois(pois: list[dict], limit: int) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for poi in pois:
        buckets.setdefault(poi.get("category", "其他"), []).append(poi)

    for bucket in buckets.values():
        bucket.sort(key=lambda p: (float(p.get("rating") or 0), -float(p.get("avg_cost") or 0)), reverse=True)

    order = ["景点", "餐厅", "咖啡", "展览", "购物", "公园", "甜品", "娱乐", "夜景", "其他"]
    result = []
    while len(result) < limit and any(buckets.values()):
        progressed = False
        for category in order:
            bucket = buckets.get(category)
            if bucket:
                result.append(bucket.pop(0))
                progressed = True
                if len(result) >= limit:
                    break
        if not progressed:
            break
    return result[:limit]


def _infer_category(poi_type: str, keyword: str = "") -> str:
    text = f"{poi_type} {keyword}".lower()
    if any(word in text for word in ["咖啡", "coffee", "茶"]):
        return "咖啡"
    if any(word in text for word in ["博物馆", "展览", "美术", "艺术"]):
        return "展览"
    if any(word in text for word in ["电竞", "电玩", "网咖", "网吧", "桌游", "密室", "剧本杀", "游戏", "娱乐", "游乐", "攀岩", "运动"]):
        return "娱乐"
    if any(word in text for word in ["餐饮", "餐厅", "美食", "饭店", "小吃"]):
        return "餐厅"
    if any(word in text for word in ["景点", "风景", "旅游", "公园", "风景名胜"]):
        return "公园" if "公园" in text else "景点"
    if any(word in text for word in ["购物", "商场", "步行街", "百货"]):
        return "购物"
    if any(word in text for word in ["甜品", "蛋糕", "面包"]):
        return "甜品"
    if any(word in text for word in ["酒吧", "夜景", "观景"]):
        return "夜景"
    return "景点"


def _is_noise_poi(poi: dict) -> bool:
    text = f"{poi.get('name', '')} {poi.get('type', '')} {poi.get('address', '')}"
    name = str(poi.get("name", ""))
    noise_words = [
        "公交站", "地铁站", "停车场", "停车位", "出入口", "卫生间", "售票处", "检票口", "服务区",
        "酒店", "民宿", "客栈", "宾馆", "旅馆", "住宿", "公寓", "售楼处", "房产小区",
        "演出公司", "演出设备", "演出器材", "设备租赁", "器材租赁", "灯光音响", "舞台设备",
        "有限公司", "科技公司", "餐饮管理", "企业管理", "文化传播",
    ]
    if any(word in text for word in noise_words):
        return True
    if re.fullmatch(r"[\u4e00-\u9fa5]{2,12}(市|区|县|自治县|自治州|地区|盟)", name):
        return True
    return False
