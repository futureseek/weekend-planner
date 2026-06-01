import json
import os
import requests
from langchain_core.tools import tool

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "api_config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _config = json.load(f)

AMAP_KEY = _config.get("amap_key", "")
BASE_URL = "https://restapi.amap.com/v3"


def _amap_get(path: str, params: dict, timeout: int = 8) -> dict:
    payload = {"key": AMAP_KEY, **{k: v for k, v in params.items() if v not in (None, "")}}
    res = requests.get(f"{BASE_URL}{path}", params=payload, timeout=timeout)
    return res.json()


def _normalize_text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


def _extract_poi(poi: dict) -> dict:
    biz = poi.get("biz_ext", {}) or {}
    return {
        "id": poi.get("id"),
        "name": poi.get("name"),
        "address": _normalize_text(poi.get("address")),
        "rating": biz.get("rating", ""),
        "cost": biz.get("cost", ""),
        "location": poi.get("location"),
        "type": poi.get("type"),
        "adcode": poi.get("adcode"),
        "pname": poi.get("pname"),
        "cityname": _normalize_text(poi.get("cityname")),
        "adname": _normalize_text(poi.get("adname")),
    }


@tool
def geocode_location(address: str, city: str = "") -> str:
    """把全国任意城市、区县、景区或地址解析为高德坐标和 adcode。"""
    data = _amap_get("/geocode/geo", {"address": address, "city": city}, timeout=8)
    if data.get("status") != "1":
        return json.dumps({"error": data.get("info", "地理编码失败")}, ensure_ascii=False)

    geocodes = []
    for item in data.get("geocodes", [])[:5]:
        geocodes.append({
            "formatted_address": item.get("formatted_address"),
            "country": item.get("country"),
            "province": item.get("province"),
            "city": _normalize_text(item.get("city")),
            "district": _normalize_text(item.get("district")),
            "adcode": item.get("adcode"),
            "location": item.get("location"),
            "level": item.get("level"),
        })
    return json.dumps(geocodes, ensure_ascii=False)


@tool
def reverse_geocode(location: str) -> str:
    """把经纬度坐标解析为省市区地址。location 格式为"经度,纬度"。"""
    data = _amap_get(
        "/geocode/regeo",
        {
            "location": location,
            "extensions": "base",
            "radius": 1000,
        },
        timeout=8,
    )
    if data.get("status") != "1":
        return json.dumps({"error": data.get("info", "逆地理编码失败")}, ensure_ascii=False)

    regeocode = data.get("regeocode", {}) or {}
    address = regeocode.get("addressComponent", {}) or {}
    payload = {
        "formatted_address": regeocode.get("formatted_address", ""),
        "province": address.get("province", ""),
        "city": _normalize_text(address.get("city")) or _normalize_text(address.get("province")),
        "district": _normalize_text(address.get("district")),
        "township": _normalize_text(address.get("township")),
        "adcode": address.get("adcode", ""),
        "location": location,
    }
    return json.dumps(payload, ensure_ascii=False)


@tool
def district_search(keyword: str, subdistrict: int = 0) -> str:
    """查询全国行政区，支持省、市、区县、县级市、自治州等名称。"""
    data = _amap_get(
        "/config/district",
        {
            "keywords": keyword,
            "subdistrict": subdistrict,
            "extensions": "base",
        },
        timeout=8,
    )
    if data.get("status") != "1":
        return json.dumps({"error": data.get("info", "行政区查询失败")}, ensure_ascii=False)

    districts = []
    for item in data.get("districts", [])[:10]:
        districts.append({
            "name": item.get("name"),
            "adcode": item.get("adcode"),
            "center": item.get("center"),
            "level": item.get("level"),
            "citycode": item.get("citycode"),
        })
    return json.dumps(districts, ensure_ascii=False)


@tool
def search_poi(keyword: str, city: str, types: str = "") -> str:
    """搜索指定城市中的兴趣点（餐厅、咖啡店、景点等）。

    Args:
        keyword: 搜索关键词，如"咖啡店"、"艺术展"、"火锅"
        city: 城市名，如"杭州"、"北京"
        types: 可选，POI类型编码。不填则按关键词搜索。
               常用类型：餐厅=050000, 咖啡=050301, 景点=110000, 博物馆=110100, 商场=060100, 电影院=080600, 公园=110101

    Returns:
        JSON格式的地点列表，包含名称、地址、评分、人均消费、坐标
    """
    params = {
        "keywords": keyword,
        "city": city,
        "offset": 10,
        "page": 1,
        "citylimit": "false",
    }
    if types:
        params["types"] = types

    data = _amap_get("/place/text", params, timeout=8)

    if data.get("status") != "1":
        return json.dumps({"error": data.get("info", "请求失败")}, ensure_ascii=False)

    pois = [_extract_poi(poi) for poi in data.get("pois", [])[:10]]

    return json.dumps(pois, ensure_ascii=False)


@tool
def search_nearby(location: str, keyword: str, radius: int = 2000) -> str:
    """搜索指定坐标附近的兴趣点。

    Args:
        location: 中心点坐标，格式"经度,纬度"，如"120.148792,30.247173"
        keyword: 搜索关键词，如"餐厅"、"咖啡店"
        radius: 搜索半径（米），默认2000米

    Returns:
        JSON格式的地点列表，包含名称、地址、评分、距离、坐标
    """
    params = {
        "location": location,
        "keywords": keyword,
        "radius": radius,
        "offset": 10,
        "page": 1,
    }

    data = _amap_get("/place/around", params, timeout=8)

    if data.get("status") != "1":
        return json.dumps({"error": data.get("info", "请求失败")}, ensure_ascii=False)

    pois = []
    for poi in data.get("pois", [])[:10]:
        item = _extract_poi(poi)
        item["distance"] = poi.get("distance")
        pois.append(item)

    return json.dumps(pois, ensure_ascii=False)



@tool
def batch_search_poi(keywords: list[str], city: str) -> str:
    """批量搜索多个关键词的地点，一次性返回所有候选地点。

    Args:
        keywords: 搜索关键词列表，如["咖啡店", "美术馆", "餐厅"]
        city: 城市名，如"杭州"

    Returns:
        JSON格式的地点列表，每个地点包含名称、地址、评分、人均消费、坐标、来源关键词
    """
    all_pois = []
    for kw in keywords:
        params = {
            "keywords": kw,
            "city": city,
            "offset": 5,
            "page": 1,
            "citylimit": "false",
        }
        try:
            data = _amap_get("/place/text", params, timeout=5)
            if data.get("status") == "1":
                for poi in data.get("pois", [])[:5]:
                    item = _extract_poi(poi)
                    item["keyword"] = kw
                    all_pois.append(item)
        except Exception:
            pass

    return json.dumps(all_pois, ensure_ascii=False)


@tool
def plan_route(locations: list[str], names: list[str] = []) -> str:
    """计算一组地点之间的路线，自动根据距离选择出行方式。

    按顺序计算相邻地点之间的距离和时间。出行方式自动判断：
    - 2km以内：步行
    - 2-10km：骑行
    - 10km以上：驾车

    Args:
        locations: 坐标列表，按游览顺序排列，格式["经度,纬度", "经度,纬度", ...]
        names: 可选，地点名称列表，与locations一一对应，用于输出可读性

    Returns:
        JSON格式的路线列表，每条包含起终点、距离、时间、出行方式
    """
    routes = []
    for i in range(len(locations) - 1):
        origin = locations[i]
        dest = locations[i + 1]
        from_name = names[i] if i < len(names) else f"地点{i + 1}"
        to_name = names[i + 1] if i + 1 < len(names) else f"地点{i + 2}"

        if not origin or not dest:
            routes.append({"from": from_name, "to": to_name, "error": "缺少坐标"})
            continue

        # 先用步行试，根据距离决定出行方式
        best_route = None
        for mode, endpoint in [("walking", "/v3/direction/walking"), ("bicycling", "/v3/direction/bicycling"), ("driving", "/v3/direction/driving")]:
            url = f"https://restapi.amap.com{endpoint}"
            params = {"key": AMAP_KEY, "origin": origin, "destination": dest}
            try:
                res = requests.get(url, params=params, timeout=5)
                data = res.json()
                if data.get("status") == "1":
                    route_data = data.get("route", {})
                    paths = route_data.get("paths", [])
                    if paths:
                        path = paths[0]
                        dist = int(path.get("distance", 0))
                        dur = int(path.get("duration", 0))
                        best_route = {
                            "from": from_name,
                            "to": to_name,
                            "distance": dist,
                            "distance_text": f"{dist}米",
                            "duration": dur,
                            "duration_text": f"{dur // 60}分钟",
                            "mode": mode,
                        }
                        break
            except Exception:
                continue

        if best_route:
            routes.append(best_route)
        else:
            routes.append({"from": from_name, "to": to_name, "error": "路线计算失败"})

    return json.dumps(routes, ensure_ascii=False)


def get_all_tools():
    """返回所有可用的工具列表"""
    return [geocode_location, reverse_geocode, district_search, search_poi, search_nearby, batch_search_poi, plan_route]
