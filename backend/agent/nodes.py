import json
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .state import PlannerState
from .context import build_context
from .agent import PlannerAgent
from tools.tavily import search_reviews


def _log(node: str, msg: str):
    print(f"[{node}] {msg}")


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
    _log("intent", f"进入意图识别, 消息数={len(state.get('messages', []))}")
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
        _log("intent", "JSON解析失败，默认intent=plan")
        return {"intent": "plan"}

    result = {
        "intent": data.get("intent", "plan"),
        "force_generate": data.get("force_generate", False),
    }

    for field in ["location", "budget", "preferences", "people_count", "time_slot"]:
        val = data.get(field)
        if val is not None and val != "null":
            result[field] = val

    _log("intent", f"结果: intent={result['intent']}, location={result.get('location')}, budget={result.get('budget')}, force={result.get('force_generate')}")
    return result


def check_node(state: PlannerState) -> dict:
    required = ["location", "time_slot"]
    has_required = all(state.get(f) for f in required)
    has_optional = bool(state.get("budget") or state.get("preferences"))
    info_complete = has_required and has_optional

    _log("check", f"完整性检查: location={state.get('location')}, time={state.get('time_slot')}, budget={state.get('budget')}, prefs={state.get('preferences')} → complete={info_complete}, ask_count={state.get('ask_count', 0)}")

    return {
        "info_complete": info_complete,
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
    _log("ask", f"追问完成, ask_count={state.get('ask_count', 0) + 1}")

    return {
        "messages": [AIMessage(content=response.content)],
        "ask_count": state.get("ask_count", 0) + 1,
    }


def social_agent_node(state: PlannerState, agent: PlannerAgent) -> dict:
    _log("social", "进入社媒搜索节点")
    result = agent.run(state)
    # 从 Agent 的最后一条消息中提取总结文本
    summary = ""
    for msg in reversed(result.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content:
            summary = msg.content
            break
    _log("social", f"社媒搜索完成, 结果长度={len(summary)}")
    return {"social_recommendations": summary}


def generate_node(state: PlannerState, agent: PlannerAgent) -> dict:
    _log("generate", "进入生成节点，交由 Agent 执行")
    result = agent.run(state)
    _log("generate", f"Agent 完成, itinerary={'有' if result.get('itinerary') else '无'}")
    return result


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
