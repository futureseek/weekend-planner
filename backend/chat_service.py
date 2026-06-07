import copy
import re

from langchain_core.messages import HumanMessage, AIMessage

from agent import build_graph, PlannerState
import agent.nodes as planner_nodes
from db.database import execute_one, execute_write
from services.route_optimizer import build_route_matrix, optimize_route
from services.poi_service import get_poi_by_id


DEFAULT_STATE = {
    "turn_number": 0,
    "intent": "plan",
    "location": None,
    "budget": None,
    "preferences": [],
    "people_count": None,
    "time_slot": None,
    "ask_count": 0,
    "info_complete": False,
    "force_generate": False,
    "social_recommendations": "",
    "itinerary": None,
    # 新增字段
    "constraints": None,
    "candidate_pois": [],
    "area_info": None,
    "alternative_plans": [],
    "event_suggestions": [],
    "upgrade_suggestions": [],
    "guide_signals": {},
    "modify_action": None,
    "modify_payload": None,
}


FOOD_CATEGORIES = {"餐厅", "咖啡", "甜品"}


def _normalize_name(value: str | None) -> str:
    return "".join(str(value or "").lower().split())


def _family_key(item: dict) -> str:
    name = str(item.get("name") or "")
    category = str(item.get("category") or "")
    base = re.split(r"[（(\[]", name, maxsplit=1)[0]
    base = re.sub(r"(总店|旗舰店|分店|门店|直营店|体验店|专卖店|加盟店)$", "", base)
    base = re.sub(r"(广州|深圳|上海|北京|杭州|成都|重庆|武汉|南京|苏州|西安|天津|厦门|青岛|佛山|东莞)", "", base)
    base = _normalize_name(base) or _normalize_name(name)
    return f"{category}:{base}"


def _route_blocks(itinerary: dict | None) -> list[dict]:
    if not isinstance(itinerary, dict):
        return []
    blocks = itinerary.get("blocks") or []
    if not blocks and itinerary.get("days"):
        for day in itinerary.get("days") or []:
            blocks.extend(day.get("blocks") or [])
    return [block for block in blocks if isinstance(block, dict) and not block.get("is_start")]


def _route_signature(items: list[dict]) -> tuple[str, ...]:
    return tuple(
        _normalize_name(item.get("id")) or _normalize_name(item.get("name"))
        for item in items
        if item.get("id") or item.get("name")
    )


def _restaurant_signature(items: list[dict]) -> tuple[str, ...]:
    return tuple(
        _family_key(item)
        for item in items
        if item.get("category") == "餐厅"
    )


def _payload_itinerary(payload: dict | None, fallback: dict | None) -> dict:
    payload = payload or {}
    current = payload.get("current_itinerary")
    return current if isinstance(current, dict) else (fallback or {})


def _budget_limit_value(constraints: dict | None) -> int | None:
    try:
        budget = int((constraints or {}).get("budget") or 0)
    except (TypeError, ValueError):
        budget = 0
    return budget if budget > 0 else None


def _itinerary_price(itinerary: dict | None) -> int:
    if not isinstance(itinerary, dict):
        return 0
    try:
        total = int(itinerary.get("total_price") or 0)
    except (TypeError, ValueError):
        total = 0
    if total > 0:
        return total
    return sum(
        int(block.get("price") or 0)
        for block in (itinerary.get("blocks") or [])
        if isinstance(block, dict)
    )


def _itinerary_within_budget(itinerary: dict | None, constraints: dict | None) -> bool:
    budget = _budget_limit_value(constraints)
    return budget is None or _itinerary_price(itinerary) <= budget


def _budget_safe_adjust_reply(language: str) -> str:
    if language == "en":
        return "No suitable adjustment was found within the current budget, so the current route was kept."
    return "当前预算内暂时找不到合适的替换方案，已保留原路线。"


def _filter_replace_candidates(pois: list[dict], current_blocks: list[dict], payload: dict | None) -> list[dict]:
    payload = payload or {}
    target_category = str(payload.get("category") or "餐厅")
    target_categories = {target_category}
    if target_category in {"餐厅", "美食", "food", "restaurant"}:
        target_categories = {"餐厅"}

    target_blocks = [block for block in current_blocks if block.get("category") in target_categories]
    if not target_blocks and target_category in {"餐厅", "美食", "food", "restaurant"}:
        target_blocks = [block for block in current_blocks if block.get("category") in FOOD_CATEGORIES]

    excluded_ids = {_normalize_name(block.get("id")) for block in target_blocks if block.get("id")}
    excluded_names = {_normalize_name(block.get("name")) for block in target_blocks if block.get("name")}
    excluded_families = {_family_key(block) for block in target_blocks}

    if not excluded_ids and not excluded_names and not excluded_families:
        return pois

    filtered = []
    for poi in pois:
        poi_id = _normalize_name(poi.get("id"))
        poi_name = _normalize_name(poi.get("name"))
        poi_family = _family_key(poi)
        if poi_id in excluded_ids or poi_name in excluded_names or poi_family in excluded_families:
            continue
        filtered.append(poi)
    return filtered


def _plan_route(plan: dict) -> list[dict]:
    return [item for item in plan.get("route", []) if isinstance(item, dict)]


def _select_adjusted_plan(plans: list[dict], preferred_style: str | None, current_blocks: list[dict], action: str) -> int:
    current_sig = _route_signature(current_blocks)
    current_restaurants = set(_restaurant_signature(current_blocks))

    def changed(plan: dict) -> bool:
        route = _plan_route(plan)
        if not route:
            return False
        if _route_signature(route) == current_sig:
            return False
        if action == "replace_poi" and current_restaurants:
            route_restaurants = set(_restaurant_signature(route))
            if not route_restaurants or current_restaurants & route_restaurants:
                return False
        return True

    candidates = list(enumerate(plans))
    if preferred_style:
        preferred = [(idx, plan) for idx, plan in candidates if plan.get("style") == preferred_style]
        for idx, plan in preferred:
            if changed(plan):
                return idx
        if preferred:
            return preferred[0][0]

    for idx, plan in candidates:
        if changed(plan):
            return idx
    return 0


class ChatService:
    def __init__(self, config: dict):
        self.graph = build_graph(config)

    def _get_config(self, session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

    def _action_message(self, action: str, payload: dict | None = None, language: str = "zh") -> str:
        payload = payload or {}
        if language == "en":
            messages = {
                "less_walking": "Please reduce walking and keep the route compact.",
                "less_queue": "Please avoid crowded or queue-heavy places.",
                "lower_budget": "Please make the route better value and reduce cost.",
                "replace_poi": f"Please replace the {payload.get('category', 'restaurant')} in this route.",
            }
            return messages.get(action, f"Please adjust the route: {action}")

        messages = {
            "less_walking": "我不想走太多路，请帮我重新规划，选近一点的地点",
            "less_queue": "我不想排队，请帮我重新规划，避开排队多的地方",
            "lower_budget": "请帮我提高性价比，重新分配预算",
            "replace_poi": f"请帮我换掉行程中的{payload.get('category', '餐厅')}",
        }
        return messages.get(action, f"请帮我调整行程：{action}")

    def chat(self, message: str, session_id: str = "default") -> dict:
        config = self._get_config(session_id)

        current = self.graph.get_state(config)
        if not current.values:
            input_state = {
                **DEFAULT_STATE,
                "thread_id": session_id,
                "messages": [HumanMessage(content=message)],
            }
        else:
            input_state = {
                "messages": [HumanMessage(content=message)],
            }

        result = self.graph.invoke(input_state, config)

        reply = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                reply = msg.content
                break

        return {
            "reply": reply,
            "itinerary": result.get("itinerary"),
            "alternatives": result.get("alternative_plans", []),
            "intent": result.get("intent"),
        }

    def chat_stream(self, message: str, session_id: str = "default"):
        result = self.chat(message, session_id)
        reply = result["reply"]

        for i in range(0, len(reply), 3):
            yield reply[i:i+3]

    def reorder(self, blocks: list[dict], session_id: str = "default") -> dict:
        config = self._get_config(session_id)
        current = self.graph.get_state(config)

        # 获取当前约束中的交通方式
        constraints = current.values.get("constraints", {}) if current.values else {}
        transport_mode = constraints.get("transport_mode", "walking")
        # 用真实路线矩阵计算连接（blocks 没有 lng/lat，需要从数据库查）
        poi_list = []
        for b in blocks:
            poi = get_poi_by_id(b["id"])
            if poi:
                poi_list.append(poi)
            else:
                # fallback：用 block 数据构造（无坐标时跳过矩阵计算）
                poi_list.append(b)

        matrix = build_route_matrix(poi_list, transport_mode)
        new_connections = planner_nodes._build_connections(
            poi_list,
            matrix,
            transport_mode,
            constraints,
            include_details=False,
        )

        total_duration = sum(b.get("duration", 0) for b in blocks)
        total_price = sum(b.get("price", 0) for b in blocks)

        new_itinerary = {
            "blocks": blocks,
            "connections": new_connections,
            "total_duration": total_duration,
            "total_price": total_price,
        }

        self.graph.update_state(config, {"itinerary": new_itinerary})

        return {
            "reply": "已按新顺序重新规划行程！",
            "itinerary": new_itinerary,
        }

    def _fast_adjust(self, action: str, current_values: dict, payload: dict | None = None) -> dict | None:
        payload = payload or {}
        constraints = copy.deepcopy(current_values.get("constraints") or {})
        pois = current_values.get("candidate_pois") or []
        if not constraints or not pois:
            return None

        language = constraints.get("language", "zh")
        itinerary = _payload_itinerary(payload, current_values.get("itinerary") or {})
        current_itinerary = itinerary
        current_blocks = _route_blocks(itinerary)
        max_stops = max(4, min(7, len(current_blocks) or 6))
        constraints["_fast_adjust"] = True
        constraints["modify_action"] = action
        constraints["modify_payload"] = payload

        if action == "less_walking":
            constraints["distance_weight_boost"] = max(float(constraints.get("distance_weight_boost") or 1.0), 4.2)
            constraints["pace"] = "relaxed"
        elif action == "lower_budget":
            constraints["budget_level"] = "budget"
            constraints["budget_target_ratio"] = min(float(constraints.get("budget_target_ratio") or 0.7), 0.58)
        elif action == "less_queue":
            constraints["avoid_queue"] = True
            preferences = list(constraints.get("preferences") or [])
            if "少排队" not in preferences:
                preferences.append("少排队")
            constraints["preferences"] = preferences
        elif action == "replace_poi":
            payload = {**payload, "category": payload.get("category") or "餐厅"}
            constraints["modify_payload"] = payload
            pois = _filter_replace_candidates(pois, current_blocks, payload)
            preferences = list(constraints.get("preferences") or [])
            if "美食" not in preferences:
                preferences.append("美食")
            constraints["preferences"] = preferences

        area_info = current_values.get("area_info") or {}
        area_center = area_info.get("center")
        opt_result = optimize_route(
            pois,
            constraints,
            max_stops=max_stops,
            area_center=area_center,
        )
        plans = opt_result.get("plans") or []
        if not plans:
            return None

        preferred_style = {
            "less_walking": "short_walk",
            "lower_budget": "budget",
            "less_queue": "balanced",
            "replace_poi": "food_fun",
        }.get(action)
        selected_index = _select_adjusted_plan(plans, preferred_style, current_blocks, action)

        selected_plan = plans[selected_index]
        ordered_plans = [selected_plan] + [plan for index, plan in enumerate(plans) if index != selected_index]
        people_count = max(1, int(constraints.get("people_count") or 1))
        shared_kwargs = {
            "matrix": opt_result.get("matrix") or {},
            "constraints": constraints,
            "people_count": people_count,
            "transport_mode": constraints.get("transport_mode", "walking"),
            "event_suggestions": current_values.get("event_suggestions", []),
            "upgrade_suggestions": current_values.get("upgrade_suggestions", []),
            "guide_signals": current_values.get("guide_signals", {}),
            "all_pois": pois,
            "include_route_details": False,
            "include_start_detail": True,
        }
        built_itineraries = []
        for plan in ordered_plans:
            candidate_itinerary = planner_nodes.build_itinerary_from_plan(plan, **shared_kwargs)
            if _itinerary_within_budget(candidate_itinerary, constraints):
                built_itineraries.append(candidate_itinerary)

        if not built_itineraries:
            if _itinerary_within_budget(current_itinerary, constraints):
                return {
                    "message": self._action_message(action, payload, language),
                    "reply": _budget_safe_adjust_reply(language),
                    "itinerary": current_itinerary,
                    "alternatives": [
                        alt for alt in (current_itinerary.get("alternatives") or [])
                        if _itinerary_within_budget(alt, constraints)
                    ],
                    "constraints": constraints,
                }
            return {
                "message": self._action_message(action, payload, language),
                "reply": _budget_safe_adjust_reply(language),
                "itinerary": None,
                "alternatives": [],
                "constraints": constraints,
            }

        new_itinerary = built_itineraries[0]
        alternatives = built_itineraries[1:4]
        new_itinerary["alternatives"] = alternatives

        return {
            "message": self._action_message(action, payload, language),
            "reply": "已重新调整路线。" if language != "en" else "Route adjusted.",
            "itinerary": new_itinerary,
            "alternatives": alternatives,
            "constraints": constraints,
        }

    def adjust(self, action: str, session_id: str = "default", payload: dict = None) -> dict:
        """动态调整路线：构造自然语言消息，通过 Agent 系统走完整管线"""
        config = self._get_config(session_id)
        current = self.graph.get_state(config)

        if not current.values or not current.values.get("itinerary"):
            return {"reply": "当前没有可调整的行程，请先规划一条路线。"}

        fast_result = self._fast_adjust(action, current.values, payload)
        if fast_result and fast_result.get("itinerary"):
            self.graph.update_state(config, {
                "constraints": fast_result["constraints"],
                "itinerary": fast_result["itinerary"],
                "alternative_plans": fast_result.get("alternatives", []),
                "modify_action": action,
                "modify_payload": payload or {},
            })
            return {key: value for key, value in fast_result.items() if key != "constraints"}

        message = self._action_message(
            action,
            payload,
            (current.values.get("constraints") or {}).get("language", "zh"),
        )

        # 将 modify_action 写入 state，供 collect_data_node 使用
        self.graph.update_state(config, {
            "modify_action": action,
            "modify_payload": payload or {},
        })

        # 通过 Agent 系统发送消息，走 intent → check → collect → rank → optimize → explain
        result = self.graph.invoke(
            {"messages": [HumanMessage(content=message)]},
            config,
        )

        reply = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage):
                reply = msg.content
                break

        return {
            "message": message,
            "reply": reply or "已重新规划行程！",
            "itinerary": result.get("itinerary"),
            "alternatives": result.get("alternative_plans", []),
        }
