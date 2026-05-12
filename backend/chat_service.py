from langchain_core.messages import HumanMessage, AIMessage

from agent import build_graph, PlannerState


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

        old_itinerary = current.values.get("itinerary", {}) if current.values else {}
        old_connections = old_itinerary.get("connections", [])

        conn_map = {}
        for c in old_connections:
            key = (c["from"], c["to"])
            conn_map[key] = c

        new_connections = []
        for i in range(len(blocks) - 1):
            from_id = blocks[i]["id"]
            to_id = blocks[i + 1]["id"]
            key = (from_id, to_id)
            if key in conn_map:
                new_connections.append(conn_map[key])
            else:
                new_connections.append({
                    "from": from_id,
                    "to": to_id,
                    "distance": "未知",
                    "time": "未知",
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
