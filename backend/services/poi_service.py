import json
import uuid
from db.database import execute_query, execute_one, execute_write, execute_many
from tools.amap import search_poi, search_nearby


# 偏好到关键词的映射
PREFERENCE_KEYWORDS = {
    "探店": ["咖啡店", "特色小店", "甜品"],
    "看展": ["美术馆", "博物馆", "展览"],
    "美食": ["餐厅", "本地菜", "小吃"],
    "亲子": ["公园", "亲子乐园", "博物馆"],
    "夜景": ["夜景", "酒吧", "观景台"],
    "咖啡": ["咖啡店", "咖啡馆"],
    "购物": ["商场", "购物中心"],
    "自然": ["公园", "景区", "湖"],
}

# 偏好到类别的映射
PREFERENCE_CATEGORIES = {
    "美食": ["餐厅", "甜品"],
    "咖啡": ["咖啡"],
    "看展": ["展览"],
    "自然": ["公园", "景点"],
    "购物": ["购物"],
}


def get_poi_by_id(poi_id: str) -> dict | None:
    """根据 ID 获取 POI"""
    return execute_one("SELECT * FROM poi WHERE id = ?", (poi_id,))


def search_local_pois(city: str = None, category: str = None, tags: list[str] = None,
                      max_cost: float = None, limit: int = 20) -> list[dict]:
    """从本地数据库查询 POI"""
    conditions = []
    params = []

    if city:
        # 城市模糊匹配：杭州西湖 -> 杭州
        city_clean = city.replace("市", "").replace("区", "")
        if "杭州" in city_clean:
            city_clean = "杭州"
        elif "北京" in city_clean:
            city_clean = "北京"
        elif "上海" in city_clean:
            city_clean = "上海"
        conditions.append("city = ?")
        params.append(city_clean)

    if category:
        conditions.append("category = ?")
        params.append(category)

    if max_cost is not None:
        conditions.append("(avg_cost <= ? OR avg_cost = 0)")
        params.append(max_cost)

    if tags:
        for tag in tags:
            conditions.append("tags LIKE ?")
            params.append(f"%{tag}%")

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""
    SELECT * FROM poi
    WHERE {where_clause}
    ORDER BY rating DESC, popularity DESC
    LIMIT ?
    """
    params.append(limit)

    return execute_query(sql, tuple(params))


def search_pois_by_preferences(city: str, preferences: list[str],
                               max_cost: float = None, limit: int = 15) -> list[dict]:
    """根据用户偏好搜索本地 POI"""
    categories = []
    for pref in preferences:
        categories.extend(PREFERENCE_CATEGORIES.get(pref, []))

    if not categories:
        # 没有特定偏好，返回评分最高的
        return search_local_pois(city=city, max_cost=max_cost, limit=limit)

    all_pois = []
    seen_ids = set()

    for cat in categories:
        pois = search_local_pois(city=city, category=cat, max_cost=max_cost, limit=5)
        for poi in pois:
            if poi["id"] not in seen_ids:
                all_pois.append(poi)
                seen_ids.add(poi["id"])

    return all_pois[:limit]


def fetch_and_save_pois_from_amap(keyword: str, city: str, limit: int = 5) -> list[dict]:
    """从高德搜索 POI 并存入本地数据库"""
    # 城市名清理
    city_clean = city.replace("市", "").replace("区", "")
    if "杭州" in city_clean:
        city_clean = "杭州"
    elif "北京" in city_clean:
        city_clean = "北京"
    elif "上海" in city_clean:
        city_clean = "上海"

    result = search_poi.invoke({"keyword": keyword, "city": city_clean})
    pois_data = json.loads(result)

    if "error" in pois_data:
        return []

    saved_pois = []
    for poi in pois_data[:limit]:
        # 检查是否已存在（按名称和坐标去重）
        existing = execute_one(
            "SELECT id FROM poi WHERE name = ? AND ABS(lng - ?) < 0.0001 AND ABS(lat - ?) < 0.0001",
            (poi["name"], float(poi["location"].split(",")[0]), float(poi["location"].split(",")[1]))
        )

        if existing:
            saved_pois.append(get_poi_by_id(existing["id"]))
            continue

        # 新 POI，存入数据库
        poi_id = f"poi_{uuid.uuid4().hex[:8]}"
        lng, lat = poi["location"].split(",")

        # 根据类型推断类别
        category = _infer_category(poi.get("type", ""))

        execute_write("""
            INSERT INTO poi (id, source, source_id, name, city, adcode, address, lng, lat, category, tags, rating, avg_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            poi_id,
            "amap",
            None,
            poi["name"],
            city_clean,
            "330100",
            poi.get("address", ""),
            float(lng),
            float(lat),
            category,
            json.dumps([keyword], ensure_ascii=False),
            float(poi.get("rating", 0)) if poi.get("rating") else None,
            float(poi.get("cost", 0)) if poi.get("cost") else None,
        ))

        saved_pois.append(get_poi_by_id(poi_id))

    return saved_pois


def search_or_fetch_pois(city: str, preferences: list[str], max_cost: float = None,
                         limit: int = 15) -> list[dict]:
    """搜索或补全 POI：先查本地，不足时从高德补全"""
    # 先查本地
    local_pois = search_pois_by_preferences(city, preferences, max_cost, limit)

    if len(local_pois) >= 5:
        return local_pois

    # 本地不足，从高德补全
    keywords_to_search = []
    for pref in preferences:
        keywords_to_search.extend(PREFERENCE_KEYWORDS.get(pref, [pref]))

    # 去重
    keywords_to_search = list(set(keywords_to_search))[:3]

    seen_names = {poi["name"] for poi in local_pois}
    fetched_pois = []

    for keyword in keywords_to_search:
        pois = fetch_and_save_pois_from_amap(keyword, city, limit=3)
        for poi in pois:
            if poi and poi["name"] not in seen_names:
                fetched_pois.append(poi)
                seen_names.add(poi["name"])

    result = local_pois + fetched_pois
    return result[:limit]


def _infer_category(poi_type: str) -> str:
    """根据高德 POI 类型推断类别"""
    type_lower = poi_type.lower()
    if "餐饮" in type_lower or "餐厅" in type_lower or "美食" in type_lower:
        return "餐厅"
    elif "咖啡" in type_lower or "茶" in type_lower:
        return "咖啡"
    elif "景点" in type_lower or "风景" in type_lower:
        return "景点"
    elif "博物馆" in type_lower or "展览" in type_lower or "美术" in type_lower:
        return "展览"
    elif "购物" in type_lower or "商场" in type_lower:
        return "购物"
    elif "公园" in type_lower:
        return "公园"
    elif "甜品" in type_lower or "蛋糕" in type_lower:
        return "甜品"
    else:
        return "其他"
