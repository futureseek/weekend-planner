import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as roam_app
import chat_service as chat_module
from agent import nodes
from chat_service import _filter_replace_candidates, _payload_itinerary, _select_adjusted_plan
from services.poi_service import _build_search_keywords, _infer_category, _is_noise_poi
from services.route_optimizer import _direct_style_route, _repair_route_composition, _visit_duration_s, optimize_route, score_poi


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


def test_reverse_location_rejects_low_accuracy_coordinate():
    client = roam_app.app.test_client()

    response = client.post("/api/location/reverse", json={
        "location": "113.390521,23.065606",
        "accuracy_m": 4000,
    })

    assert response.status_code == 422
    payload = response.get_json()
    assert payload["error"] == "location accuracy is too low"
    assert payload["max_accuracy_m"] == 30


def test_reverse_location_allows_low_accuracy_for_city_only(monkeypatch):
    monkeypatch.setattr(
        roam_app,
        "reverse_geocode",
        SimpleNamespace(invoke=lambda _payload: json.dumps(
            {
                "formatted_address": "广东省广州市天河区",
                "province": "广东省",
                "city": "广州市",
                "district": "天河区",
                "adcode": "440106",
                "location": "113.361597,23.124817",
            },
            ensure_ascii=False,
        )),
    )
    monkeypatch.setattr(roam_app, "fetch_nearest_anchor", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("anchor should be skipped")))
    client = roam_app.app.test_client()

    response = client.post("/api/location/reverse", json={
        "location": "113.361597,23.124817",
        "accuracy_m": 50000,
        "city_only": True,
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["city"] == "广州市"
    assert payload["district"] == "天河区"
    assert payload["source"] == "reverse_geocode"


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


def test_start_transfer_shifts_first_day_for_cross_district_transit():
    day_plan = {
        "blocks": [
            {"id": "poi-1", "day_index": 1, "start_time": "11:00", "end_time": "12:00", "price": 0},
            {"id": "poi-2", "day_index": 1, "start_time": "12:15", "end_time": "13:00", "price": 0},
        ],
        "connections": [],
        "days": [
            {
                "day_index": 1,
                "start_time": "11:00",
                "end_time": "13:00",
                "total_duration": 120,
                "total_price": 0,
                "blocks": [
                    {"id": "poi-1", "day_index": 1, "start_time": "11:00", "end_time": "12:00", "price": 0},
                    {"id": "poi-2", "day_index": 1, "start_time": "12:15", "end_time": "13:00", "price": 0},
                ],
                "connections": [],
            }
        ],
    }

    result = nodes._apply_start_transfer_to_day_plan(day_plan, 100, {"daily_end_time": "22:00"})

    assert result["days"][0]["blocks"][0]["start_time"] == "12:40"
    assert result["days"][0]["blocks"][0]["end_time"] == "13:40"


def test_poi_noise_filter_excludes_government_offices():
    assert _is_noise_poi({
        "name": "增城区人民政府",
        "type": "政府机构及社会团体;政府机关",
        "address": "增城区",
    })
    assert _is_noise_poi({
        "name": "天河区天园街综合养老服务中心(颐康中心)",
        "type": "生活服务;养老服务",
        "address": "天河区",
    })
    assert _is_noise_poi({
        "name": "番禺区草河区级湿地公园(不对外开放)",
        "type": "风景名胜;公园广场",
        "address": "番禺区",
    })


def test_long_walking_connection_switches_to_transit():
    route = [
        {"id": "a", "name": "起点景点", "lng": 113.30, "lat": 23.10},
        {"id": "b", "name": "下一个景点", "lng": 113.33, "lat": 23.12},
    ]
    connections = nodes._build_connections(
        route,
        {("a", "b"): {"distance_m": 2100, "duration_s": 23 * 60}},
        "walking",
        {"city": "广州"},
        include_details=False,
    )

    assert connections[0]["mode"] == "公共交通"
    assert connections[0]["duration_minutes"] <= 20
    assert connections[0]["from_lng"] == 113.30
    assert connections[0]["to_lng"] == 113.33


def test_connection_minutes_parses_localized_labels_and_numeric_priority():
    assert nodes._connection_minutes({"duration_minutes": 42, "time": "1小时31分钟"}) == 42
    assert nodes._connection_minutes({"time": "1h 31min"}) == 91
    assert nodes._connection_minutes({"time": "25min"}) == 25
    assert nodes._connection_minutes({"time": "1小时"}) == 60


def test_shopping_area_duration_is_not_treated_as_quick_checkin():
    plaza = {"id": "p", "name": "番禺广场", "category": "景点", "tags": [], "address": "番禺区"}
    mall_area = {"id": "m", "name": "市桥商圈", "category": "购物", "tags": ["商圈"], "address": "番禺区"}

    assert _visit_duration_s(plaza) >= 90 * 60
    assert _visit_duration_s(mall_area) >= 100 * 60
    assert nodes._duration_for_category("景点", "番禺广场", [], "番禺区") >= 90
    assert nodes._duration_for_category("购物", "市桥商圈", ["商圈"], "番禺区") >= 100


def test_infer_category_handles_morning_tea_as_restaurant():
    assert _infer_category("餐饮服务;中餐厅", "广式早茶") == "餐厅"
    assert _infer_category("", "老字号粤菜茶楼") == "餐厅"


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


def test_fast_adjust_payload_itinerary_takes_active_plan():
    fallback = {"blocks": [{"id": "old", "name": "旧路线"}]}
    active = {"blocks": [{"id": "active", "name": "当前右侧方案"}]}

    assert _payload_itinerary({"current_itinerary": active}, fallback) is active
    assert _payload_itinerary({}, fallback) is fallback


def test_replace_poi_filters_current_restaurant_and_same_family():
    current_blocks = [
        {"id": "r1", "name": "广州酒家(天河店)", "category": "餐厅"},
        {"id": "p1", "name": "花城广场", "category": "夜景"},
    ]
    pois = [
        {"id": "r1", "name": "广州酒家(天河店)", "category": "餐厅"},
        {"id": "r2", "name": "广州酒家(越秀店)", "category": "餐厅"},
        {"id": "r3", "name": "高分粤菜馆", "category": "餐厅"},
        {"id": "p1", "name": "花城广场", "category": "夜景"},
    ]

    filtered = _filter_replace_candidates(pois, current_blocks, {"category": "餐厅"})
    names = {item["name"] for item in filtered}

    assert "广州酒家(天河店)" not in names
    assert "广州酒家(越秀店)" not in names
    assert "高分粤菜馆" in names
    assert "花城广场" in names


def test_select_adjusted_plan_skips_unchanged_and_same_restaurant():
    current_blocks = [
        {"id": "r1", "name": "广州酒家(天河店)", "category": "餐厅"},
        {"id": "p1", "name": "花城广场", "category": "夜景"},
    ]
    plans = [
        {
            "style": "food_fun",
            "route": [
                {"id": "r1", "name": "广州酒家(天河店)", "category": "餐厅"},
                {"id": "p1", "name": "花城广场", "category": "夜景"},
            ],
        },
        {
            "style": "food_fun",
            "route": [
                {"id": "r2", "name": "广州酒家(越秀店)", "category": "餐厅"},
                {"id": "p2", "name": "珠江夜游", "category": "夜景"},
            ],
        },
        {
            "style": "food_fun",
            "route": [
                {"id": "r3", "name": "高分粤菜馆", "category": "餐厅"},
                {"id": "p2", "name": "珠江夜游", "category": "夜景"},
            ],
        },
    ]

    assert _select_adjusted_plan(plans, "food_fun", current_blocks, "replace_poi") == 2


def test_fast_adjust_keeps_current_route_when_replacement_exceeds_budget(monkeypatch):
    service = chat_module.ChatService.__new__(chat_module.ChatService)
    current_itinerary = {
        "blocks": [{"id": "old-r", "name": "当前餐厅", "category": "餐厅", "price": 120}],
        "total_price": 120,
        "alternatives": [],
    }
    current_values = {
        "constraints": {"budget": 300, "people_count": 1, "language": "zh"},
        "candidate_pois": [{"id": "new-r", "name": "高价餐厅", "category": "餐厅", "avg_cost": 500}],
        "itinerary": current_itinerary,
        "area_info": {},
        "event_suggestions": [],
        "upgrade_suggestions": [],
        "guide_signals": {},
    }

    monkeypatch.setattr(
        chat_module,
        "optimize_route",
        lambda *args, **kwargs: {
            "plans": [
                {
                    "name": "吃好玩好",
                    "style": "food_fun",
                    "route": [{"id": "new-r", "name": "高价餐厅", "category": "餐厅", "avg_cost": 500}],
                    "score": {"total_cost": 500, "total_duration_s": 3600, "total_distance_m": 0, "route_score": 1},
                    "highlights": [],
                }
            ],
            "matrix": {},
        },
    )
    monkeypatch.setattr(
        chat_module.planner_nodes,
        "build_itinerary_from_plan",
        lambda *args, **kwargs: {
            "blocks": [{"id": "new-r", "name": "高价餐厅", "category": "餐厅", "price": 500}],
            "total_price": 500,
            "alternatives": [],
        },
    )

    result = service._fast_adjust("replace_poi", current_values, {"category": "餐厅"})

    assert result["itinerary"] is current_itinerary
    assert result["itinerary"]["total_price"] == 120
    assert "预算" in result["reply"]


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


def test_food_fun_direct_route_keeps_activity_mix():
    candidates = [
        {"id": "r1", "name": "高分粤菜馆", "category": "餐厅", "_score": 0.95, "avg_cost": 180},
        {"id": "r2", "name": "海鲜酒家", "category": "餐厅", "_score": 0.90, "avg_cost": 220},
        {"id": "r3", "name": "本地茶楼", "category": "餐厅", "_score": 0.86, "avg_cost": 130},
        {"id": "e1", "name": "Livehouse", "category": "娱乐", "_score": 0.84, "avg_cost": 160},
        {"id": "n1", "name": "江边夜景", "category": "夜景", "_score": 0.82, "avg_cost": 0},
        {"id": "s1", "name": "城市公园", "category": "公园", "_score": 0.80, "avg_cost": 0},
        {"id": "x1", "name": "艺术展", "category": "展览", "_score": 0.78, "avg_cost": 80},
        {"id": "c1", "name": "慢咖啡", "category": "咖啡", "_score": 0.76, "avg_cost": 45},
    ]

    route = _direct_style_route(candidates, 6, "food_fun", {"preferences": ["美食"]})

    assert sum(1 for poi in route if poi["category"] == "餐厅") <= 1
    assert sum(1 for poi in route if poi["category"] in {"娱乐", "夜景", "公园", "展览", "购物"}) >= 3


def test_search_keywords_interleave_food_and_gaming_preferences():
    keywords = _build_search_keywords(["美食", "游戏", "娱乐"], "天河区")
    first_ten = " ".join(keywords[:10])

    assert any(word in first_ten for word in ["电竞馆", "电玩", "密室逃脱", "桌游吧"])
    assert any(word in first_ten for word in ["高分餐厅", "老字号粤菜", "餐厅"])


def test_optimize_route_game_food_preference_keeps_mixed_actions():
    candidates = [
        {"id": "r1", "name": "广州酒家(广酒大厦店)", "category": "餐厅", "lng": 113.31, "lat": 23.12, "avg_cost": 110, "rating": 4.6, "tags": ["粤菜"], "review_count": 180},
        {"id": "r2", "name": "广州酒家(百福广场店)", "category": "餐厅", "lng": 113.32, "lat": 23.121, "avg_cost": 95, "rating": 4.5, "tags": ["粤菜"], "review_count": 170},
        {"id": "r3", "name": "本地高分粤菜馆", "category": "餐厅", "lng": 113.33, "lat": 23.122, "avg_cost": 130, "rating": 4.7, "tags": ["本地菜"], "review_count": 200},
        {"id": "e1", "name": "番禺电竞馆", "category": "娱乐", "lng": 113.34, "lat": 23.123, "avg_cost": 80, "rating": 4.6, "tags": ["电竞", "游戏"], "review_count": 120},
        {"id": "e2", "name": "密室逃脱", "category": "娱乐", "lng": 113.35, "lat": 23.124, "avg_cost": 98, "rating": 4.5, "tags": ["密室"], "review_count": 110},
        {"id": "n1", "name": "江边夜景", "category": "夜景", "lng": 113.36, "lat": 23.125, "avg_cost": 0, "rating": 4.5, "tags": ["夜景", "免费"], "review_count": 100},
        {"id": "m1", "name": "潮流商场", "category": "购物", "lng": 113.37, "lat": 23.126, "avg_cost": 40, "rating": 4.3, "tags": ["商场"], "review_count": 100},
        {"id": "c1", "name": "慢咖啡", "category": "咖啡", "lng": 113.38, "lat": 23.127, "avg_cost": 35, "rating": 4.4, "tags": ["咖啡"], "review_count": 90},
        {"id": "p1", "name": "城市公园", "category": "公园", "lng": 113.39, "lat": 23.128, "avg_cost": 0, "rating": 4.4, "tags": ["散步"], "review_count": 90},
    ]

    result = optimize_route(
        candidates,
        {
            "preferences": ["美食", "游戏", "娱乐", "热闹"],
            "food_priority": "quality",
            "budget": 300,
            "people_count": 1,
            "duration_minutes": 540,
            "daily_start_time": "12:00",
            "daily_end_time": "22:00",
        },
        max_stops=6,
        area_center=(113.34, 23.123),
    )

    assert result["plans"]
    for plan in result["plans"]:
        categories = [poi["category"] for poi in plan["route"]]
        names = [poi["name"] for poi in plan["route"]]
        assert len(plan["route"]) >= 4
        assert categories.count("餐厅") <= 1
        assert sum(1 for category in categories if category in {"娱乐", "夜景", "购物", "展览", "公园", "景点"}) >= 2
        assert not ("广州酒家(广酒大厦店)" in names and "广州酒家(百福广场店)" in names)


def test_repair_route_composition_drops_restaurant_stack_without_replacements():
    route = [
        {"id": "r1", "name": "酒家一", "category": "餐厅", "_score": 0.95, "avg_cost": 160},
        {"id": "r2", "name": "酒家二", "category": "餐厅", "_score": 0.90, "avg_cost": 180},
        {"id": "r3", "name": "酒家三", "category": "餐厅", "_score": 0.84, "avg_cost": 130},
    ]

    repaired = _repair_route_composition(route, route, {"preferences": ["美食"]}, "food_fun")

    assert sum(1 for poi in repaired if poi["category"] == "餐厅") <= 1

def test_optimize_route_dedupes_identical_stop_sets():
    categories = [
        "\u9910\u5385",
        "\u5496\u5561",
        "\u666f\u70b9",
        "\u5a31\u4e50",
        "\u591c\u666f",
        "\u8d2d\u7269",
        "\u5c55\u89c8",
        "\u516c\u56ed",
    ]
    costs = [120, 45, 0, 80, 0, 70, 60, 0]
    candidates = [
        {
            "id": f"poi-{index}",
            "name": f"place-{index}",
            "category": category,
            "lng": 113.30 + index * 0.004,
            "lat": 23.10 + index * 0.003,
            "avg_cost": costs[index],
            "rating": 4.5,
            "review_count": 160,
            "tags": [],
        }
        for index, category in enumerate(categories)
    ]

    result = optimize_route(
        candidates,
        {
            "preferences": ["\u7f8e\u98df", "\u591c\u666f"],
            "budget": 300,
            "people_count": 1,
            "duration_minutes": 600,
            "daily_start_time": "12:00",
            "daily_end_time": "22:00",
        },
        max_stops=5,
        area_center=(113.31, 23.11),
    )

    stop_sets = [tuple(sorted(poi["id"] for poi in plan["route"])) for plan in result["plans"]]
    assert len(stop_sets) == len(set(stop_sets))


def test_optimize_route_keeps_at_least_four_single_day_stops():
    categories = [
        "\u9910\u5385",
        "\u5496\u5561",
        "\u666f\u70b9",
        "\u5a31\u4e50",
        "\u591c\u666f",
        "\u8d2d\u7269",
        "\u5c55\u89c8",
        "\u516c\u56ed",
    ]
    candidates = [
        {
            "id": f"min-poi-{index}",
            "name": f"min-place-{index}",
            "category": category,
            "lng": 113.30 + index * 0.003,
            "lat": 23.10 + index * 0.002,
            "avg_cost": [80, 25, 0, 60, 0, 35, 40, 0][index],
            "rating": 4.5,
            "review_count": 120,
            "tags": [],
        }
        for index, category in enumerate(categories)
    ]

    result = optimize_route(
        candidates,
        {
            "preferences": ["\u7f8e\u98df", "\u591c\u666f"],
            "budget": 300,
            "people_count": 1,
            "duration_minutes": 300,
            "daily_start_time": "16:00",
            "daily_end_time": "22:00",
        },
        max_stops=5,
        area_center=(113.31, 23.11),
    )

    assert result["plans"]
    assert all(len(plan["route"]) >= 4 for plan in result["plans"])


def test_optimize_route_returns_three_distinct_mixed_single_day_plans():
    candidates = [
        {"id": "r1", "name": "高分粤菜馆", "category": "餐厅", "lng": 113.30, "lat": 23.10, "avg_cost": 130, "rating": 4.7, "review_count": 240, "tags": ["粤菜", "本地菜"]},
        {"id": "r2", "name": "广州酒家(天河店)", "category": "餐厅", "lng": 113.31, "lat": 23.101, "avg_cost": 120, "rating": 4.6, "review_count": 210, "tags": ["粤菜"]},
        {"id": "r3", "name": "广州酒家(越秀店)", "category": "餐厅", "lng": 113.32, "lat": 23.102, "avg_cost": 115, "rating": 4.5, "review_count": 180, "tags": ["粤菜"]},
        {"id": "e1", "name": "电竞体验馆", "category": "娱乐", "lng": 113.33, "lat": 23.103, "avg_cost": 80, "rating": 4.6, "review_count": 160, "tags": ["电竞", "游戏"]},
        {"id": "e2", "name": "密室逃脱", "category": "娱乐", "lng": 113.34, "lat": 23.104, "avg_cost": 98, "rating": 4.5, "review_count": 130, "tags": ["密室"]},
        {"id": "n1", "name": "江边夜景", "category": "夜景", "lng": 113.35, "lat": 23.105, "avg_cost": 0, "rating": 4.4, "review_count": 150, "tags": ["夜景"]},
        {"id": "m1", "name": "潮流商场", "category": "购物", "lng": 113.36, "lat": 23.106, "avg_cost": 40, "rating": 4.4, "review_count": 120, "tags": ["商场"]},
        {"id": "x1", "name": "艺术展", "category": "展览", "lng": 113.37, "lat": 23.107, "avg_cost": 60, "rating": 4.4, "review_count": 110, "tags": ["展览"]},
        {"id": "p1", "name": "城市公园", "category": "公园", "lng": 113.38, "lat": 23.108, "avg_cost": 0, "rating": 4.4, "review_count": 100, "tags": ["散步"]},
        {"id": "c1", "name": "慢咖啡", "category": "咖啡", "lng": 113.39, "lat": 23.109, "avg_cost": 35, "rating": 4.3, "review_count": 90, "tags": ["咖啡"]},
        {"id": "s1", "name": "甜品铺", "category": "甜品", "lng": 113.40, "lat": 23.110, "avg_cost": 30, "rating": 4.2, "review_count": 80, "tags": ["甜品"]},
    ]

    result = optimize_route(
        candidates,
        {
            "preferences": ["美食", "游戏", "夜景", "休闲"],
            "food_priority": "quality",
            "budget": 500,
            "people_count": 1,
            "duration_minutes": 600,
            "daily_start_time": "12:00",
            "daily_end_time": "22:00",
        },
        max_stops=6,
        area_center=(113.34, 23.104),
    )

    assert len(result["plans"]) >= 3
    stop_sets = [tuple(sorted(poi["id"] for poi in plan["route"])) for plan in result["plans"]]
    assert len(stop_sets) == len(set(stop_sets))
    for plan in result["plans"][:3]:
        categories = [poi["category"] for poi in plan["route"]]
        assert len(plan["route"]) >= 4
        assert categories.count("餐厅") <= 1
        assert sum(1 for category in categories if category in {"娱乐", "夜景", "购物", "展览", "公园", "景点"}) >= 2


def test_optimize_route_never_exceeds_user_budget_after_fill():
    candidates = [
        {"id": "budget-r-exp", "name": "expensive-dinner", "category": "\u9910\u5385", "lng": 113.30, "lat": 23.10, "avg_cost": 220, "rating": 4.8, "review_count": 260, "tags": ["\u7ca4\u83dc"]},
        {"id": "budget-r-ok", "name": "good-dinner", "category": "\u9910\u5385", "lng": 113.31, "lat": 23.101, "avg_cost": 120, "rating": 4.7, "review_count": 240, "tags": ["\u7ca4\u83dc"]},
        {"id": "budget-e", "name": "arcade", "category": "\u5a31\u4e50", "lng": 113.32, "lat": 23.102, "avg_cost": 90, "rating": 4.6, "review_count": 180, "tags": ["\u6e38\u620f"]},
        {"id": "budget-m", "name": "mall", "category": "\u8d2d\u7269", "lng": 113.33, "lat": 23.103, "avg_cost": 70, "rating": 4.4, "review_count": 160, "tags": ["\u5546\u573a"]},
        {"id": "budget-p", "name": "park", "category": "\u516c\u56ed", "lng": 113.34, "lat": 23.104, "avg_cost": 0, "rating": 4.4, "review_count": 140, "tags": ["\u514d\u8d39"]},
        {"id": "budget-n", "name": "night-view", "category": "\u591c\u666f", "lng": 113.35, "lat": 23.105, "avg_cost": 0, "rating": 4.5, "review_count": 130, "tags": ["\u591c\u666f", "\u514d\u8d39"]},
        {"id": "budget-x", "name": "exhibition", "category": "\u5c55\u89c8", "lng": 113.36, "lat": 23.106, "avg_cost": 20, "rating": 4.3, "review_count": 120, "tags": ["\u5c55\u89c8"]},
        {"id": "budget-c", "name": "coffee", "category": "\u5496\u5561", "lng": 113.37, "lat": 23.107, "avg_cost": 25, "rating": 4.2, "review_count": 100, "tags": ["\u5496\u5561"]},
    ]

    result = optimize_route(
        candidates,
        {
            "preferences": ["\u7f8e\u98df", "\u6e38\u620f", "\u591c\u666f", "\u4f11\u95f2"],
            "budget": 300,
            "people_count": 1,
            "duration_minutes": 600,
            "daily_start_time": "10:30",
            "daily_end_time": "22:00",
        },
        max_stops=6,
        area_center=(113.33, 23.103),
    )

    assert result["plans"]
    for plan in result["plans"]:
        assert plan["score"]["total_cost"] <= 300


def test_start_transfer_trim_preserves_four_visible_stops():
    blocks = []
    for index in range(5):
        blocks.append({
            "id": f"poi-{index}",
            "name": f"place-{index}",
            "day_index": 1,
            "start_time": f"{17 + index}:00",
            "end_time": f"{17 + index}:45",
            "price": 20,
        })
    day_plan = {
        "blocks": list(blocks),
        "connections": [],
        "days": [{
            "day_index": 1,
            "start_time": "17:00",
            "end_time": "21:45",
            "total_duration": 285,
            "total_price": 100,
            "blocks": list(blocks),
            "connections": [],
        }],
    }

    nodes._trim_day_to_end_window(
        day_plan,
        day_plan["days"][0],
        {
            "trip_days": 1,
            "duration_minutes": 300,
            "daily_end_time": "19:30",
        },
    )

    visible = [block for block in day_plan["days"][0]["blocks"] if not block.get("is_start")]
    assert len(visible) == 4
