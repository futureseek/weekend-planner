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
    "itinerary": None,
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
