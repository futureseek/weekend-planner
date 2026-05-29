from langchain_core.messages import HumanMessage, AIMessage

from agent import build_graph, PlannerState
from db.database import execute_one, execute_write
from services.route_optimizer import build_route_matrix
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
    "modify_action": None,
    "modify_payload": None,
}


class ChatService:
    def __init__(self, config: dict):
        self.graph = build_graph(config)

    def _get_config(self, session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

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
        mode_label = {"walking": "步行", "bicycling": "骑行", "driving": "驾车"}.get(transport_mode, "步行")

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

        new_connections = []
        for i in range(len(blocks) - 1):
            from_id = blocks[i]["id"]
            to_id = blocks[i + 1]["id"]
            key = (from_id, to_id)

            if key in matrix:
                dist_m = matrix[key]["distance_m"]
                dur_s = matrix[key]["duration_s"]
                distance = f"{dist_m}m" if dist_m < 1000 else f"{dist_m / 1000:.1f}km"
                minutes = dur_s // 60
                time = f"{minutes}分钟" if minutes < 60 else f"{minutes // 60}小时{minutes % 60}分钟"
            else:
                distance = "未知"
                time = "未知"

            new_connections.append({
                "from": from_id,
                "to": to_id,
                "distance": distance,
                "time": time,
                "mode": mode_label,
            })

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

    def adjust(self, action: str, session_id: str = "default", payload: dict = None) -> dict:
        """动态调整路线：构造自然语言消息，通过 Agent 系统走完整管线"""
        config = self._get_config(session_id)
        current = self.graph.get_state(config)

        if not current.values or not current.values.get("itinerary"):
            return {"reply": "当前没有可调整的行程，请先规划一条路线。"}

        # 构造自然语言消息，让用户意图清晰
        action_messages = {
            "less_walking": "我不想走太多路，请帮我重新规划，选近一点的地点",
            "less_queue": "我不想排队，请帮我重新规划，避免排队多的地方",
            "lower_budget": "请帮我省钱，降低预算重新规划",
            "replace_poi": f"请帮我换掉行程中的{(payload or {}).get('category', '餐厅')}",
        }
        message = action_messages.get(action, f"请帮我调整行程：{action}")

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
        }
