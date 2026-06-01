from dataclasses import dataclass
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage


TOKEN_BUDGET = 4000
PROTECT_RECENT = 3  # 最近N轮强制保留


@dataclass
class MessageMeta:
    message: BaseMessage
    priority: int
    token_count: int


PRIORITY_MAP = {
    "system": 100,
    "human": 90,
    "tool": 80,
    "ai_summary": 60,
    "ai_detail": 40,
    "ai_chitchat": 20,
}

SYSTEM_PROMPT = """你是"Roam 漫游"AI路线规划助手，英文场景下称为 "Roam"。
用户会告诉你他们的位置、出行人数、预算、偏好等信息。
你需要帮他们规划可执行的多目的地路线，推荐具体地点、时间安排和备选策略。
回复要简洁、明确，不要编造不存在的地点或价格。"""


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def classify_ai_message(content: str) -> int:
    if len(content) < 80:
        return PRIORITY_MAP["ai_summary"]
    if "```" in content or len(content) > 500:
        return PRIORITY_MAP["ai_detail"]
    return PRIORITY_MAP["ai_chitchat"]


def classify_message(msg: BaseMessage) -> int:
    if msg.type == "human":
        return PRIORITY_MAP["human"]
    if msg.type == "tool":
        return PRIORITY_MAP["tool"]
    if msg.type == "ai":
        return classify_ai_message(msg.content)
    return 50


def build_field_summary(state: dict) -> str:
    parts = []
    if state.get("location"):
        parts.append(f"位置={state['location']}")
    if state.get("budget"):
        parts.append(f"预算={state['budget']}元")
    if state.get("preferences"):
        parts.append(f"偏好={state['preferences']}")
    if state.get("people_count"):
        parts.append(f"人数={state['people_count']}人")
    if state.get("time_slot"):
        parts.append(f"时间={state['time_slot']}")
    if parts:
        return "已提取信息：" + "，".join(parts)
    return "尚未提取到任何信息"


def trim_by_priority(meta_list: list[MessageMeta], budget: int, protect_recent: int) -> list[MessageMeta]:
    system_msgs = []
    recent = []
    older = []

    msg_count = 0
    user_count = 0
    for m in reversed(meta_list):
        if m.priority == 100:
            system_msgs.insert(0, m)
            continue
        if user_count < protect_recent:
            recent.insert(0, m)
            if m.message.type == "human":
                user_count += 1
        else:
            older.insert(0, m)

    recent_tokens = sum(m.token_count for m in recent)
    system_tokens = sum(m.token_count for m in system_msgs)
    remaining = budget - recent_tokens - system_tokens

    if remaining <= 0:
        return system_msgs + recent

    older.sort(key=lambda m: m.priority)
    kept_older = []
    used = 0
    for m in older:
        if used + m.token_count <= remaining:
            kept_older.append(m)
            used += m.token_count

    result = system_msgs + kept_older + recent
    return result


def build_context(state: dict) -> list[BaseMessage]:
    all_meta: list[MessageMeta] = []

    summary = build_field_summary(state)
    system_content = f"{SYSTEM_PROMPT}\n\n{summary}"
    all_meta.append(MessageMeta(
        message=SystemMessage(content=system_content),
        priority=100,
        token_count=estimate_tokens(system_content),
    ))

    for msg in state.get("messages", []):
        priority = classify_message(msg)
        all_meta.append(MessageMeta(
            message=msg,
            priority=priority,
            token_count=estimate_tokens(msg.content),
        ))

    kept = trim_by_priority(all_meta, TOKEN_BUDGET, PROTECT_RECENT)
    return [m.message for m in kept]
