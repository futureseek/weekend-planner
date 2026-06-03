from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from .state import PlannerState
from . import nodes


def _build_llm(model_config: dict):
    llm_kwargs = {}
    extra_body = model_config.get("extra_body") or {}
    if extra_body and extra_body.get("thinking", {}).get("type") != "disabled":
        llm_kwargs["extra_body"] = extra_body
    if "openai.com" in str(model_config.get("base_url") or "") and model_config.get("reasoning_effort"):
        llm_kwargs["reasoning_effort"] = model_config.get("reasoning_effort")

    return ChatOpenAI(
        model=model_config["model_name"],
        api_key=model_config["api_key"],
        base_url=model_config["base_url"],
        temperature=float(model_config.get("temperature", 0.2)),
        timeout=int(model_config.get("timeout", 45)),
        max_retries=int(model_config.get("max_retries", 1)),
        **llm_kwargs,
    )


def build_graph(config: dict):
    agents = config.get("agents") or {}
    fast_llm = _build_llm(agents.get("fast") or agents.get("qa") or config)
    parser_llm = _build_llm(agents.get("parser") or agents.get("fast") or agents.get("qa") or config)
    chat_llm = _build_llm(agents.get("chat") or agents.get("fast") or agents.get("qa") or config)
    explain_llm = _build_llm(agents.get("explain") or agents.get("qa") or config)

    graph = StateGraph(PlannerState)

    # 节点
    graph.add_node("intent_node", lambda s: nodes.intent_node(s, fast_llm))
    graph.add_node("check_node", nodes.check_node)
    graph.add_node("ask_node", lambda s: nodes.ask_node(s, chat_llm))
    graph.add_node("chat_node", lambda s: nodes.chat_node(s, chat_llm))

    # 数据驱动流程
    graph.add_node("collect_data_node", lambda s: nodes.collect_data_node(s, parser_llm))
    graph.add_node("rank_poi_node", lambda s: nodes.rank_poi_node(s))
    graph.add_node("optimize_route_node", lambda s: nodes.optimize_route_node(s))
    graph.add_node("explain_node", lambda s: nodes.explain_node(s, explain_llm))

    graph.set_entry_point("intent_node")

    # 意图路由：modify 也走 check_node，由 collect_data_node 处理修改逻辑
    graph.add_conditional_edges(
        "intent_node",
        lambda s: "chat_node" if s["intent"] == "chat"
                  else "check_node",
        {
            "chat_node": "chat_node",
            "check_node": "check_node",
        },
    )

    # 信息检查路由
    graph.add_conditional_edges(
        "check_node",
        lambda s: "collect_data_node" if s["info_complete"] or s["force_generate"] or s.get("ask_count", 0) >= 3
                  else "ask_node",
        {
            "collect_data_node": "collect_data_node",
            "ask_node": "ask_node",
        },
    )

    # 数据管线：收集 → 打分 → 优化 → 解释
    graph.add_edge("collect_data_node", "rank_poi_node")
    graph.add_edge("rank_poi_node", "optimize_route_node")
    graph.add_edge("optimize_route_node", "explain_node")
    graph.add_edge("explain_node", END)

    # 闲聊和追问
    graph.add_edge("ask_node", END)
    graph.add_edge("chat_node", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
