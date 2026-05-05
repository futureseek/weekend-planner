import json
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage


MAX_TOOL_ROUNDS = 5


def _log(msg: str):
    print(f"[agent] {msg}")


GENERATE_SYSTEM = """你是行程规划助手。你有以下工具可用：
1. batch_search_poi(keywords, city) - 批量搜索地点
2. plan_route(locations, names) - 计算路线

工作流程：
1. 调用 batch_search_poi 搜索地点（将用户偏好转为关键词，如"探店"→["咖啡店","特色小店"]）
2. 从结果中挑选 3-5 个地点，如果有社媒推荐信息，需要综合判断（社媒推荐仅供参考，以 POI 搜索的实际数据为准）
3. 调用 plan_route 计算路线（只调一次）
4. 收到 plan_route 结果后，直接输出最终行程 JSON，不要再调用任何工具

重要：当你已经拿到 plan_route 的返回结果时，说明所有数据已齐备，必须立即输出最终 JSON 行程。"""

GENERATE_PROMPT = """用户信息：
- 位置：{location}
- 预算：{budget} 元
- 偏好：{preferences}
- 人数：{people_count} 人
- 时间：{time_slot}

{social_section}

请开始搜索地点。最终输出 JSON 格式：
{{
  "blocks": [
    {{
      "id": "block_1",
      "type": "cafe",
      "icon": "☕",
      "name": "活动名称",
      "duration": 60,
      "price": 45,
      "recommendation": "推荐理由",
      "address": "地址"
    }}
  ],
  "connections": [
    {{
      "from": "block_1",
      "to": "block_2",
      "distance": "500米",
      "time": "步行6分钟"
    }}
  ],
  "total_duration": 240,
  "total_price": 300
}}"""

SOCIAL_SYSTEM = """你是社媒推荐搜索助手。你只有一个工具可用：
- search_reviews(query) - 搜索地点的用户评价和推荐

工作流程：
1. 根据用户的位置和偏好，生成 2-3 个精准的搜索问题
2. 对每个问题调用 search_reviews 搜索
3. 从搜索结果中提取有价值的推荐信息，总结为一段文字

搜索问题示例：
- "杭州 探店 推荐 2024"
- "杭州 周末看展 好去处"

总结要求：
- 提取具体的地点名称、亮点、用户评价
- 标注信息来源（大众点评/抖音/小红书等）
- 直接输出总结文字，不要输出 JSON"""

SOCIAL_PROMPT_TEMPLATE = """用户出行需求：
- 位置：{location}
- 偏好：{preferences}
- 时间：{time_slot}

请根据以上信息生成 2-3 个搜索问题，调用 search_reviews 搜索，然后总结推荐结果。"""


class PlannerAgent:
    def __init__(self, llm_with_tools, tools: list, system_prompt: str = "", prompt_template: str = ""):
        self.llm = llm_with_tools
        self.tools = {t.name: t for t in tools}
        self.system_prompt = system_prompt or GENERATE_SYSTEM
        self.prompt_template = prompt_template or GENERATE_PROMPT

    def run(self, state: dict) -> dict:
        """执行工具调用循环，返回最终结果。"""
        _log("进入 Agent 执行循环")

        # 构建 prompt
        social_section = ""
        if state.get("social_recommendations"):
            social_section = f"""以下是搜索引擎找到的社媒推荐（来自大众点评、抖音等平台），仅供参考，需要和 POI 搜索结果综合判断：
---
{state["social_recommendations"]}
---"""

        prompt = self.prompt_template.format(
            location=state.get("location") or "未知",
            budget=state.get("budget") or "不限",
            preferences=state.get("preferences") or "无特别偏好",
            people_count=state.get("people_count") or "未知",
            time_slot=state.get("time_slot") or "周末",
            social_section=social_section,
        )

        agent_messages: list[BaseMessage] = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        has_plan_route = False

        for round_num in range(1, MAX_TOOL_ROUNDS + 1):
            _log(f"第 {round_num} 轮 LLM 调用")
            response = self.llm.invoke(agent_messages)

            if not response.tool_calls:
                _log(f"LLM 无工具调用，结束循环 (共 {round_num} 轮)")
                itinerary = self._try_parse_itinerary(response.content)
                return {
                    "messages": [AIMessage(content=response.content if not itinerary else "帮你规划好了！以下是行程方案：")],
                    "itinerary": itinerary,
                }

            agent_messages.append(response)
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                _log(f"  执行工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:80]})")

                tool_fn = self.tools.get(tool_name)
                if tool_fn:
                    result = tool_fn.invoke(tool_args)
                else:
                    result = json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

                agent_messages.append(ToolMessage(
                    content=result,
                    tool_call_id=tc["id"],
                ))

                if tool_name == "plan_route":
                    has_plan_route = True

            if has_plan_route:
                _log("已拿到路线结果，提示 LLM 输出最终行程")
                agent_messages.append(SystemMessage(
                    content="plan_route 已返回结果，所有数据已齐备。请不要再调用任何工具，直接输出最终行程 JSON。"
                ))

        _log(f"达到最大轮次 {MAX_TOOL_ROUNDS}")
        for msg in reversed(agent_messages):
            if isinstance(msg, AIMessage) and msg.content:
                itinerary = self._try_parse_itinerary(msg.content)
                return {
                    "messages": [AIMessage(content=msg.content if not itinerary else "帮你规划好了！以下是行程方案：")],
                    "itinerary": itinerary,
                }

        return {
            "messages": [AIMessage(content="抱歉，生成行程时遇到了问题，请重试。")],
            "itinerary": None,
        }

    def _try_parse_itinerary(self, content: str) -> dict | None:
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "blocks" in data:
                return data
        except json.JSONDecodeError:
            pass
        return None
