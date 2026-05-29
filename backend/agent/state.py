from typing import TypedDict, Annotated
from langgraph.graph import add_messages


class PlannerState(TypedDict):
    # 对话管理
    thread_id: str
    turn_number: int
    messages: Annotated[list, add_messages]

    # 意图
    intent: str  # plan / modify / chat

    # 结构化字段
    location: str | None
    budget: int | None
    preferences: list[str]
    people_count: int | None
    time_slot: str | None

    # 流程控制
    ask_count: int
    info_complete: bool
    force_generate: bool

    # 社媒推荐
    social_recommendations: str

    # 输出
    itinerary: dict | None

    # 新增：数据驱动流程
    constraints: dict | None
    candidate_pois: list[dict]
    area_info: dict | None
    alternative_plans: list[dict]

    # 修改动作
    modify_action: str | None
    modify_payload: dict | None
