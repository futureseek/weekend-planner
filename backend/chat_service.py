from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


SYSTEM_PROMPT = """你是"周末去哪儿"AI行程规划助手。
用户会告诉你他们的位置、出行人数、预算、偏好等信息。
你需要帮他们规划周末行程，推荐具体的地点和活动。
回复要简洁友好，带有emoji，突出亮点。"""


class ChatService:
    def __init__(self, config: dict):
        self.llm = ChatOpenAI(
            model=config["model_name"],
            api_key=config["api_key"],
            base_url=config["base_url"],
            temperature=0.7,
        )
        self.sessions: dict[str, list] = {}

    def _get_history(self, session_id: str) -> list:
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        return self.sessions[session_id]

    def chat(self, message: str, session_id: str = "default") -> str:
        history = self._get_history(session_id)

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for msg in history:
            messages.append(msg)
        messages.append(HumanMessage(content=message))

        response = self.llm.invoke(messages)
        reply = response.content

        history.append(HumanMessage(content=message))
        history.append(AIMessage(content=reply))

        return reply

    def chat_stream(self, message: str, session_id: str = "default"):
        history = self._get_history(session_id)

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        for msg in history:
            messages.append(msg)
        messages.append(HumanMessage(content=message))

        full_reply = ""
        for chunk in self.llm.stream(messages):
            content = chunk.content
            full_reply += content
            yield content

        history.append(HumanMessage(content=message))
        history.append(AIMessage(content=full_reply))
