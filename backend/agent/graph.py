from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI

from .state import PlannerState
from . import nodes


def build_graph(config: dict):
    llm = ChatOpenAI(
        model=config["model_name"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=0.7,
    )

    graph = StateGraph(PlannerState)

    graph.add_node("intent_node", lambda s: nodes.intent_node(s, llm))
    graph.add_node("check_node", nodes.check_node)
    graph.add_node("ask_node", lambda s: nodes.ask_node(s, llm))
    graph.add_node("generate_node", lambda s: nodes.generate_node(s, llm))
    graph.add_node("modify_node", lambda s: nodes.modify_node(s, llm))
    graph.add_node("chat_node", lambda s: nodes.chat_node(s, llm))

    graph.set_entry_point("intent_node")

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

    graph.add_conditional_edges(
        "check_node",
        lambda s: "generate_node" if s["info_complete"] or s["force_generate"] or s.get("ask_count", 0) >= 3
                  else "ask_node",
        {
            "generate_node": "generate_node",
            "ask_node": "ask_node",
        },
    )

    graph.add_edge("ask_node", END)
    graph.add_edge("generate_node", END)
    graph.add_edge("modify_node", END)
    graph.add_edge("chat_node", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
