import json
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from config import load_config
from chat_service import ChatService
from db.database import init_db
from db.seed import seed_pois
from tools.amap import reverse_geocode, district_search, geocode_location, input_tips, search_poi
from tools.xhs_ugc import search_xhs_public_notes, read_public_webpage

app = Flask(__name__)
CORS(app)

# 初始化数据库
init_db()
seed_pois()

config = load_config()
chat_service = ChatService(config)


CITY_ALIASES = {
    "guangzhou": "广州",
    "canton": "广州",
    "shanghai": "上海",
    "beijing": "北京",
    "shenzhen": "深圳",
    "chengdu": "成都",
    "hangzhou": "杭州",
    "nanjing": "南京",
    "suzhou": "苏州",
    "chongqing": "重庆",
    "wuhan": "武汉",
    "xian": "西安",
    "xi'an": "西安",
    "xiamen": "厦门",
    "lhasa": "拉萨",
    "kashgar": "喀什",
    "urumqi": "乌鲁木齐",
}


def normalize_city_name(city: str) -> str:
    value = (city or "").strip().replace("市", "")
    return CITY_ALIASES.get(value.lower(), value)


def _text_value(value) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


def _poi_geocode_item(item: dict) -> dict | None:
    location = item.get("location")
    if not location:
        return None
    city = _text_value(item.get("cityname"))
    district = _text_value(item.get("adname"))
    name = _text_value(item.get("name"))
    address = _text_value(item.get("address"))
    return {
        "name": name,
        "formatted_address": " ".join(part for part in [_text_value(item.get("pname")), city, district, name] if part),
        "address": address,
        "city": city,
        "district": district,
        "adcode": item.get("adcode", ""),
        "location": location,
        "level": item.get("type", "POI"),
        "type": item.get("type", ""),
        "rating": item.get("rating", ""),
        "cost": item.get("cost", ""),
        "source": "poi",
    }


def _tip_geocode_item(item: dict, city: str = "") -> dict | None:
    location = item.get("location")
    if not location:
        return None
    district_text = _text_value(item.get("district"))
    name = _text_value(item.get("name"))
    address = _text_value(item.get("address"))
    display_city = city or ""
    return {
        "name": name,
        "formatted_address": " ".join(part for part in [district_text, name] if part),
        "address": address,
        "city": display_city,
        "district": district_text,
        "adcode": item.get("adcode", ""),
        "location": location,
        "level": "POI",
        "type": item.get("typecode", ""),
        "source": "tip",
    }


def _geo_geocode_item(item: dict) -> dict | None:
    if not item.get("location"):
        return None
    return {
        "name": _text_value(item.get("formatted_address")),
        "formatted_address": _text_value(item.get("formatted_address")),
        "address": _text_value(item.get("formatted_address")),
        "city": _text_value(item.get("city")),
        "district": _text_value(item.get("district")),
        "adcode": item.get("adcode", ""),
        "location": item.get("location", ""),
        "level": item.get("level", ""),
        "source": "geocode",
    }


def _rank_location_suggestion(item: dict, keyword: str, city: str) -> tuple[int, int, int]:
    name = _text_value(item.get("name") or item.get("formatted_address"))
    address = _text_value(item.get("formatted_address")) + _text_value(item.get("address"))
    source = item.get("source")
    level = _text_value(item.get("level"))
    normalized_city = city.replace("市", "")
    item_city = _text_value(item.get("city")).replace("市", "")
    district = _text_value(item.get("district"))
    score = 0
    if source in {"poi", "tip"}:
        score += 140
    if source == "tip":
        score += 25
    if keyword and name == keyword:
        score += 135
    elif keyword and name.startswith(keyword):
        score += 65
    elif keyword and keyword in name:
        score += 50
    elif keyword and keyword in address:
        score += 25
    if normalized_city and (normalized_city in item_city or normalized_city in district or normalized_city in address):
        score += 35
    if any(word in level for word in ["商务住宅", "科教文化", "学校", "大学", "餐饮", "购物", "风景名胜", "生活服务"]):
        score += 20
    if "高等院校" in level:
        score += 25
    if any(word in name for word in ["大学", "学院", "学校", "校区", "公园", "商场", "广场", "酒店", "餐厅", "咖啡", "景区"]):
        score += 18
    if keyword and "大学" in keyword and any(word in name for word in ["校区", "校园"]):
        score += 65
    if keyword and "大学" in keyword and any(word in name for word in ["学院", "教学楼", "科技综合楼", "办公楼", "宿舍", "食堂", "文科楼", "中大西北区"]):
        score -= 80
    if keyword and "大学" in keyword and any(word in name for word in ["附属", "医院", "小学", "中学", "停车", "公交"]):
        score -= 45
    if level in {"市", "省", "国家", "区县", "乡镇"}:
        score -= 95
    if source == "geocode":
        score -= 15
    source_rank = 0 if source in {"tip", "poi"} else 1
    return (-score, source_rank, len(name))


def _merge_location_items(items: list[dict], keyword: str, city: str) -> list[dict]:
    deduped = []
    seen = set()
    for item in items:
        location = item.get("location")
        key = (location, _text_value(item.get("name") or item.get("formatted_address")).lower())
        if not location or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda item: _rank_location_suggestion(item, keyword, city))
    return deduped


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400

    result = chat_service.chat(message, session_id)
    return jsonify({
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
        "alternatives": result.get("alternatives", []),
        "intent": result.get("intent"),
    })


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "message is required"}), 400

    def generate():
        for chunk in chat_service.chat_stream(message, session_id):
            yield f"data: {json.dumps({'content': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/api/reorder", methods=["POST"])
def reorder():
    data = request.get_json(silent=True) or {}
    blocks = data.get("blocks", [])
    session_id = data.get("session_id", "default")

    if not blocks:
        return jsonify({"error": "blocks is required"}), 400

    result = chat_service.reorder(blocks, session_id)
    return jsonify({
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
    })


@app.route("/api/itinerary/adjust", methods=["POST"])
def adjust_itinerary():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "").strip()
    session_id = data.get("session_id", "default")
    payload = data.get("payload", {})

    if not action:
        return jsonify({"error": "action is required"}), 400

    result = chat_service.adjust(action, session_id, payload)
    return jsonify({
        "message": result.get("message", ""),
        "reply": result["reply"],
        "itinerary": result.get("itinerary"),
        "alternatives": result.get("alternatives", []),
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/location/reverse", methods=["POST"])
def reverse_location():
    data = request.get_json(silent=True) or {}
    location = data.get("location", "").strip()

    if not location:
        return jsonify({"error": "location is required"}), 400

    result = reverse_geocode.invoke({"location": location})
    payload = json.loads(result)
    status = 400 if payload.get("error") else 200
    return jsonify(payload), status


@app.route("/api/location/geocode", methods=["POST"])
def geocode():
    data = request.get_json(silent=True) or {}
    address = (data.get("address") or data.get("keyword") or "").strip()
    city = normalize_city_name(data.get("city") or "")

    if not address:
        return jsonify({"error": "address is required"}), 400

    items = []
    poi_queries = [(address, city)]
    if city:
        poi_queries.append((address, ""))
        if city not in address:
            poi_queries.append((f"{city}{address}", ""))

    try:
        tip_payload = json.loads(input_tips.invoke({"keyword": address, "city": city}))
        if isinstance(tip_payload, list):
            items.extend(item for item in (_tip_geocode_item(tip, city) for tip in tip_payload) if item)
    except Exception:
        pass

    try:
        for query, query_city in poi_queries:
            poi_payload = json.loads(search_poi.invoke({"keyword": query, "city": query_city}))
            if isinstance(poi_payload, list):
                items.extend(item for item in (_poi_geocode_item(poi) for poi in poi_payload) if item)
    except Exception:
        pass

    try:
        geo_payload = json.loads(geocode_location.invoke({"address": address, "city": city}))
        if isinstance(geo_payload, list):
            items.extend(item for item in (_geo_geocode_item(geo) for geo in geo_payload) if item)
    except Exception:
        pass

    return jsonify({"items": _merge_location_items(items, address, city)[:8]})


@app.route("/api/location/districts", methods=["POST"])
def city_districts():
    data = request.get_json(silent=True) or {}
    city = normalize_city_name(data.get("city") or data.get("keyword") or "")

    if not city:
        return jsonify({"error": "city is required"}), 400

    result = district_search.invoke({"keyword": city, "subdistrict": 1})
    payload = json.loads(result)
    if isinstance(payload, dict) and payload.get("error"):
        return jsonify(payload), 400

    districts = []
    for item in payload if isinstance(payload, list) else []:
        children = item.get("districts") or []
        if children:
            districts.extend(children)
        elif item.get("level") in {"district", "区县"}:
            districts.append(item)

    normalized = []
    seen = set()
    for item in districts:
        name = item.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        normalized.append({
            "name": name,
            "adcode": item.get("adcode", ""),
            "center": item.get("center", ""),
            "level": item.get("level", ""),
        })

    return jsonify({"city": city, "districts": normalized})


@app.route("/api/ugc/xhs/search", methods=["POST"])
def search_xhs_ugc():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    limit = data.get("limit", 5)

    if not query:
        return jsonify({"error": "query is required"}), 400

    result = search_xhs_public_notes.invoke({"query": query, "limit": limit})
    return jsonify({"items": json.loads(result)})


@app.route("/api/ugc/read-page", methods=["POST"])
def read_ugc_page():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    max_chars = data.get("max_chars", 4000)

    if not url:
        return jsonify({"error": "url is required"}), 400

    result = read_public_webpage.invoke({"url": url, "max_chars": max_chars})
    payload = json.loads(result)
    status = 400 if payload.get("error") else 200
    return jsonify(payload), status


if __name__ == "__main__":
    app.run(debug=True, port=5000, use_reloader=False)
