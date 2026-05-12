from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from .state import PlannerState
from .agent import PlannerAgent, SOCIAL_SYSTEM, SOCIAL_PROMPT_TEMPLATE
from . import nodes
from tools import get_all_tools
from tools.tavily import search_reviews


def build_graph(config: dict):
    llm = ChatOpenAI(
        model=config["model_name"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=0.7,
    )

    # 社媒搜索 Agent：只绑定 search_reviews 工具
    social_llm_with_tools = llm.bind_tools([search_reviews])
    social_agent = PlannerAgent(
        llm_with_tools=social_llm_with_tools,
        tools=[search_reviews],
        system_prompt=SOCIAL_SYSTEM,
        prompt_template=SOCIAL_PROMPT_TEMPLATE,
    )

    # 行程生成 Agent：绑定 Amap 工具（保留兼容）
    tools = get_all_tools()
    llm_with_tools = llm.bind_tools(tools)
    generate_agent = PlannerAgent(llm_with_tools, tools)

    graph = StateGraph(PlannerState)

    # 原有节点
    graph.add_node("intent_node", lambda s: nodes.intent_node(s, llm))
    graph.add_node("check_node", nodes.check_node)
    graph.add_node("ask_node", lambda s: nodes.ask_node(s, llm))
    graph.add_node("social_agent_node", lambda s: nodes.social_agent_node(s, social_agent))
    graph.add_node("generate_node", lambda s: nodes.generate_node(s, generate_agent))
    graph.add_node("modify_node", lambda s: nodes.modify_node(s, llm))
    graph.add_node("chat_node", lambda s: nodes.chat_node(s, llm))

    # 新增节点：数据驱动流程
    graph.add_node("collect_data_node", lambda s: nodes.collect_data_node(s, llm))
    graph.add_node("rank_poi_node", lambda s: nodes.rank_poi_node(s))
    graph.add_node("optimize_route_node", lambda s: nodes.optimize_route_node(s))
    graph.add_node("explain_node", lambda s: nodes.explain_node(s, llm))

    graph.set_entry_point("intent_node")

    # 意图路由
    graph.add_conditional_edges(
        "intent_node",
        lambda s: "chat_node" if s["intent"] == "chat"
                  else "modify_node" if s["intent"] == "modify"
                  else "check_node",
        {
            "chat_node": "chat_node",
            "modify_node": "modify_node",
            "check_node": "check_node",
        },
    )

    # 信息检查路由：走新流程
    graph.add_conditional_edges(
        "check_node",
        lambda s: "collect_data_node" if s["info_complete"] or s["force_generate"] or s.get("ask_count", 0) >= 3
                  else "ask_node",
        {
            "collect_data_node": "collect_data_node",
            "ask_node": "ask_node",
        },
    )

    # 新流程：数据收集 → 打分 → 优化 → 解释
    graph.add_edge("collect_data_node", "rank_poi_node")
    graph.add_edge("rank_poi_node", "optimize_route_node")
    graph.add_edge("optimize_route_node", "explain_node")
    graph.add_edge("explain_node", END)

    # 原有流程
    graph.add_edge("ask_node", END)
    graph.add_edge("generate_node", END)
    graph.add_edge("modify_node", END)
    graph.add_edge("chat_node", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
