import json
from langchain_core.messages import HumanMessage, AIMessage

from .state import PlannerState
from .context import build_context


INTENT_PROMPT = """你是行程规划助手的意图识别模块。从用户消息中提取结构化信息。

当前已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

用户最新消息：{message}

请严格返回 JSON（不要有其他内容）：
{{
  "intent": "plan" 或 "modify" 或 "chat",
  "location": "位置，没提到则保持原值",
  "budget": 预算数字（int），没提到则保持原值,
  "preferences": ["偏好列表"],没提到则保持原值,
  "people_count": 人数（int），没提到则保持原值,
  "time_slot": "时间段"，没提到则保持原值,
  "force_generate": true 或 false
}}

规则：
- intent=plan：用户在描述出行需求
- intent=modify：用户想修改已有行程（如"换个餐厅"、"去掉这个地方"）
- intent=chat：闲聊（天气、笑话等与行程无关的）
- 用户说"就这样"/"随便"/"不用问了"/"直接生成"时 force_generate=true
- 只更新用户这次明确提到的字段，没提到的保持原值（用null表示未提到）"""

ASK_PROMPT = """你是行程规划助手，现在需要向用户确认一些信息。

已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

缺失的关键信息：{missing}

请用自然友好的方式，一次性询问缺失信息（最多问2个问题）。
要求：口语化、简短、有emoji。不要重复已知信息。"""

GENERATE_PROMPT = """你是行程规划助手，现在需要为用户生成一份周末行程。

用户信息：
- 位置：{location}
- 预算：{budget} 元
- 偏好：{preferences}
- 人数：{people_count} 人
- 时间：{time_slot}

请生成一份行程方案。要求：
1. 安排 3-5 个活动，时间合理衔接
2. 每个活动给出推荐理由（口语化、有亮点）
3. 总预算不超过用户预算

请返回 JSON 格式（不要有其他内容）：
{{
  "blocks": [
    {{
      "id": "block_1",
      "type": "cafe",
      "icon": "☕",
      "name": "活动名称",
      "duration": 60,
      "price": 45,
      "recommendation": "推荐理由，20字以内，口语化",
      "address": "大概地址"
    }}
  ],
  "connections": [
    {{
      "from": "block_1",
      "to": "block_2",
      "distance": "1.2km",
      "time": "15min"
    }}
  ],
  "total_duration": 240,
  "total_price": 300
}}"""

MODIFY_PROMPT = """用户想修改现有行程。

当前行程：
{current_itinerary}

用户修改要求：{message}

请只修改用户提到的部分，保持其他内容不变。
返回与之前相同格式的 JSON 行程。"""

CHAT_PROMPT = """你是"周末去哪儿"AI行程规划助手。
用户在和你闲聊，请简短友好地回复，并自然地引导用户描述出行需求。
保持在2-3句话以内。"""


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def intent_node(state: PlannerState, llm) -> dict:
    context = build_context(state)
    prompt = INTENT_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "未知",
        preferences=state.get("preferences") or "未知",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "未知",
        message=state["messages"][-1].content,
    )

    response = llm.invoke(context + [HumanMessage(content=prompt)])
    data = _parse_json(response.content)

    if not data:
        return {"intent": "plan"}

    result = {
        "intent": data.get("intent", "plan"),
        "force_generate": data.get("force_generate", False),
    }

    for field in ["location", "budget", "preferences", "people_count", "time_slot"]:
        val = data.get(field)
        if val is not None and val != "null":
            result[field] = val

    return result


def check_node(state: PlannerState) -> dict:
    required = ["location", "time_slot"]
    has_required = all(state.get(f) for f in required)
    has_optional = bool(state.get("budget") or state.get("preferences"))

    return {
        "info_complete": has_required and has_optional,
        "turn_number": state.get("turn_number", 0) + 1,
    }


def ask_node(state: PlannerState, llm) -> dict:
    missing = []
    if not state.get("location"):
        missing.append("位置/城市")
    if not state.get("budget"):
        missing.append("预算")
    if not state.get("preferences"):
        missing.append("偏好（如探店、看展、美食等）")
    if not state.get("time_slot"):
        missing.append("出行时间")

    context = build_context(state)
    prompt = ASK_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "未知",
        preferences=state.get("preferences") or "未知",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "未知",
        missing="、".join(missing),
    )

    response = llm.invoke(context + [HumanMessage(content=prompt)])

    return {
        "messages": [AIMessage(content=response.content)],
        "ask_count": state.get("ask_count", 0) + 1,
    }


def generate_node(state: PlannerState, llm) -> dict:
    context = build_context(state)
    prompt = GENERATE_PROMPT.format(
        location=state.get("location") or "未知",
        budget=state.get("budget") or "不限",
        preferences=state.get("preferences") or "无特别偏好",
        people_count=state.get("people_count") or "未知",
        time_slot=state.get("time_slot") or "周末",
    )

    response = llm.invoke(context + [HumanMessage(content=prompt)])
    itinerary = _parse_json(response.content)

    if itinerary:
        reply = "帮你规划好了！以下是行程方案："
        return {
            "messages": [AIMessage(content=reply)],
            "itinerary": itinerary,
        }

    return {
        "messages": [AIMessage(content=response.content)],
        "itinerary": None,
    }


def modify_node(state: PlannerState, llm) -> dict:
    context = build_context(state)
    prompt = MODIFY_PROMPT.format(
        current_itinerary=json.dumps(state.get("itinerary"), ensure_ascii=False, indent=2),
        message=state["messages"][-1].content,
    )

    response = llm.invoke(context + [HumanMessage(content=prompt)])
    itinerary = _parse_json(response.content)

    if itinerary:
        reply = "已更新行程方案！"
        return {
            "messages": [AIMessage(content=reply)],
            "itinerary": itinerary,
        }

    return {
        "messages": [AIMessage(content=response.content)],
    }


def chat_node(state: PlannerState, llm) -> dict:
    context = build_context(state)
    response = llm.invoke(context + [HumanMessage(content=CHAT_PROMPT)])

    return {
        "messages": [AIMessage(content=response.content)],
    }
