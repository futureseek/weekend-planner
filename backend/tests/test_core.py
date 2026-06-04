import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as roam_app
from agent import nodes
from services.route_optimizer import _repair_route_composition, score_poi


def setup_function():
    roam_app._DISTRICT_CACHE.clear()
    roam_app._GEOCODE_CACHE.clear()


def test_health_endpoint():
    client = roam_app.app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_districts_fallback_when_amap_unavailable(monkeypatch):
    def fail(_payload):
        raise RuntimeError("amap down")

    monkeypatch.setattr(roam_app, "district_search", SimpleNamespace(invoke=fail))
    client = roam_app.app.test_client()

    response = client.post("/api/location/districts", json={"city": "广州"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["source"] == "fallback"
    assert {"name": "天河区", "adcode": "", "center": "", "level": "district"} in payload["districts"]
    assert {"name": "番禺区", "adcode": "", "center": "", "level": "district"} in payload["districts"]


def test_geocode_merges_and_ranks_poi_results(monkeypatch):
    monkeypatch.setattr(
        roam_app,
        "input_tips",
        SimpleNamespace(invoke=lambda _payload: json.dumps(
            [
                {
                    "name": "中山大学广州校区南校园",
                    "location": "113.293201,23.096250",
                    "district": "广东省广州市海珠区",
                    "address": "新港西路135号",
                    "typecode": "141201",
                }
            ],
            ensure_ascii=False,
        )),
    )
    monkeypatch.setattr(
        roam_app,
        "search_poi",
        SimpleNamespace(invoke=lambda _payload: json.dumps(
            [
                {
                    "name": "中山大学",
                    "location": "113.293201,23.096250",
                    "pname": "广东省",
                    "cityname": "广州市",
                    "adname": "海珠区",
                    "address": "新港西路135号",
                    "type": "科教文化服务;学校;高等院校",
                },
                {
                    "name": "中山大学附属医院",
                    "location": "113.290000,23.120000",
                    "pname": "广东省",
                    "cityname": "广州市",
                    "adname": "越秀区",
                    "address": "医院路",
                    "type": "医疗保健服务",
                },
            ],
            ensure_ascii=False,
        )),
    )
    monkeypatch.setattr(roam_app, "geocode_location", SimpleNamespace(invoke=lambda _payload: "[]"))
    client = roam_app.app.test_client()

    response = client.post("/api/location/geocode", json={"city": "广州", "address": "中山大学"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"]
    assert payload["items"][0]["name"] in {"中山大学", "中山大学广州校区南校园"}
    assert all(item["location"] for item in payload["items"])


def test_reverse_location_prefers_nearest_anchor_within_20m(monkeypatch):
    monkeypatch.setattr(
        roam_app,
        "reverse_geocode",
        SimpleNamespace(invoke=lambda _payload: json.dumps(
            {
                "formatted_address": "广东省广州市番禺区",
                "province": "广东省",
                "city": "广州市",
                "district": "番禺区",
                "adcode": "440113",
                "location": "113.390521,23.065606",
            },
            ensure_ascii=False,
        )),
    )
    monkeypatch.setattr(
        roam_app,
        "fetch_nearest_anchor",
        lambda _location, radius=20: {
            "name": "广州番禺广场地铁站A口",
            "address": "番禺广场附近",
            "pname": "广东省",
            "cityname": "广州市",
            "adname": "番禺区",
            "adcode": "440113",
            "location": "113.390600,23.065610",
            "distance_m": 9,
        },
    )
    client = roam_app.app.test_client()

    response = client.post("/api/location/reverse", json={"location": "113.390521,23.065606"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["name"] == "广州番禺广场地铁站A口"
    assert payload["location"] == "113.390600,23.065610"
    assert payload["original_location"] == "113.390521,23.065606"
    assert payload["anchor_distance_m"] == 9
    assert payload["source"] == "nearest_poi_20m"


def test_start_transfer_is_not_dropped_for_long_distance():
    transfer = nodes._build_start_transfer(
        {
            "start_location": "116.397128,39.916527",
            "start_location_label": "北京天安门",
            "language": "zh",
        },
        {
            "id": "poi-1",
            "name": "广州塔",
            "lng": 113.330934,
            "lat": 23.113401,
        },
    )

    assert transfer is not None
    assert transfer["from"] == "start"
    assert transfer["mode"] == "跨城接驳"
    assert transfer["distance_m"] > 1_000_000


def test_start_block_is_injected_before_first_stop():
    day_plan = {
        "blocks": [
            {
                "id": "poi-1",
                "name": "广州塔",
                "lng": 113.330934,
                "lat": 23.113401,
                "day_index": 1,
                "start_time": "18:30",
                "end_time": "19:30",
                "price": 150,
            }
        ],
        "connections": [],
        "days": [
            {
                "day_index": 1,
                "start_time": "18:30",
                "end_time": "19:30",
                "total_duration": 60,
                "total_price": 150,
                "blocks": [
                    {
                        "id": "poi-1",
                        "name": "广州塔",
                        "lng": 113.330934,
                        "lat": 23.113401,
                        "day_index": 1,
                        "start_time": "18:30",
                        "end_time": "19:30",
                        "price": 150,
                    }
                ],
                "connections": [],
            }
        ],
    }
    transfer = {
        "from": "start",
        "from_name": "当前位置附近",
        "to": "poi-1",
        "to_name": "广州塔",
        "distance": "3.0km",
        "distance_m": 3000,
        "time": "20分钟",
        "duration_minutes": 20,
        "mode": "公共交通",
    }

    result = nodes._inject_start_block(day_plan, transfer, {"start_location": "113.31,23.12"})

    assert result["blocks"][0]["id"] == "start"
    assert result["days"][0]["blocks"][0]["is_start"] is True
    assert result["connections"][0]["from"] == "start"


def test_upgrade_suggestions_filter_bad_evening_candidates():
    pois = [
        {
            "name": "广州市天河区文化馆",
            "category": "景点",
            "address": "天河区公共文化服务",
            "rating": 4.8,
            "avg_cost": 180,
            "tags": ["文化馆"],
        },
        {
            "name": "MAO Livehouse广州",
            "category": "娱乐",
            "address": "天河区音乐现场",
            "rating": 4.6,
            "avg_cost": 220,
            "tags": ["Livehouse", "演出"],
        },
        {
            "name": "高分粤菜馆",
            "category": "餐厅",
            "address": "天河区",
            "rating": 4.7,
            "avg_cost": 180,
            "tags": ["粤菜"],
        },
    ]

    suggestions = nodes._build_upgrade_suggestions(
        pois,
        {
            "language": "zh",
            "people_count": 1,
            "budget": 300,
            "preferences": ["美食", "夜景"],
            "daily_start_time": "18:30",
            "daily_end_time": "22:00",
        },
        limit=4,
    )

    names = [item["title"] for item in suggestions]
    assert "广州市天河区文化馆" not in names
    assert "MAO Livehouse广州" in names
    assert "高分粤菜馆" in names


def test_adjust_endpoint_returns_service_payload(monkeypatch):
    monkeypatch.setattr(
        roam_app.chat_service,
        "adjust",
        lambda action, session_id, payload: {
            "message": f"adjust:{action}",
            "reply": "ok",
            "itinerary": {"blocks": [], "connections": [], "total_duration": 0, "total_price": 0},
            "alternatives": [],
        },
    )
    client = roam_app.app.test_client()

    response = client.post("/api/itinerary/adjust", json={"action": "less_walking", "session_id": "s1"})

    assert response.status_code == 200
    assert response.get_json()["reply"] == "ok"


def test_local_explanation_hides_internal_fit_check():
    itinerary = {
        "plan_name": "综合推荐",
        "blocks": [{"name": "高分粤菜馆", "category": "餐厅", "tags": ["粤菜"]}],
        "total_duration": 90,
        "total_price": 180,
    }

    text = nodes._local_explanation(
        itinerary,
        [],
        {"language": "zh", "budget": 300, "people_count": 1, "preferences": ["美食"]},
    )

    assert "方案自检" not in text
    assert "Fit Check" not in text


def test_quality_food_preference_penalizes_low_value_chain():
    constraints = {
        "preferences": ["美食"],
        "food_priority": "quality",
        "budget": 500,
        "people_count": 1,
        "guide_positive_keywords": ["粤菜", "本地人推荐"],
        "guide_avoid_keywords": ["快餐"],
    }
    quality = {
        "name": "本地高分粤菜酒家",
        "category": "餐厅",
        "address": "广州",
        "tags": ["粤菜", "本地人推荐"],
        "rating": 4.6,
        "avg_cost": 160,
    }
    low_value = {
        "name": "萨莉亚",
        "category": "餐厅",
        "address": "广州",
        "tags": ["快餐"],
        "rating": 4.6,
        "avg_cost": 45,
    }

    assert score_poi(quality, constraints) > score_poi(low_value, constraints)


def test_repair_route_composition_limits_restaurant_stack():
    route = [
        {"id": "r1", "name": "餐厅1", "category": "餐厅", "_score": 0.4, "avg_cost": 120},
        {"id": "r2", "name": "餐厅2", "category": "餐厅", "_score": 0.5, "avg_cost": 130},
        {"id": "r3", "name": "餐厅3", "category": "餐厅", "_score": 0.6, "avg_cost": 150},
        {"id": "e1", "name": "娱乐1", "category": "娱乐", "_score": 0.7, "avg_cost": 120},
    ]
    candidates = route + [
        {"id": "p1", "name": "公园", "category": "公园", "_score": 0.8, "avg_cost": 0},
        {"id": "x1", "name": "展览", "category": "展览", "_score": 0.7, "avg_cost": 80},
    ]

    repaired = _repair_route_composition(route, candidates, {"preferences": ["美食"]}, "food_fun")

    assert sum(1 for poi in repaired if poi["category"] == "餐厅") <= 1
    assert any(poi["category"] in {"公园", "展览", "娱乐"} for poi in repaired)
