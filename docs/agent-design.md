# Agent 设计文档 — 周末去哪儿 AI 行程规划

## 1. 整体架构

```
前端 (Next.js)
     │
     │ POST /api/chat
     ↓
Flask 后端
     │
     │ thread_id + message
     ↓
LangGraph Agent
     │
     ├─ 意图识别节点（LLM）
     ├─ 完整性检查节点（Python）
     ├─ 追问节点（LLM）
     └─ 生成行程节点（LLM + Tools）
     │
     │ itinerary JSON
     ↓
返回前端
```

---

## 2. 状态定义

```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages

class PlannerState(TypedDict):
    # 对话管理
    thread_id: str                          # 对话窗口唯一ID
    turn_number: int                        # 当前轮次
    messages: Annotated[list, add_messages] # 完整对话历史（checkpoint存储）

    # 意图
    intent: str                             # plan / modify / chat

    # 结构化字段（累积提取，每轮更新）
    location: str | None                    # 位置，如"杭州西湖"
    budget: int | None                      # 预算，如 300
    preferences: list[str]                  # 偏好，如["探店", "看展"]
    people_count: int | None                # 人数，如 2
    time_slot: str | None                   # 时间，如"周六下午"

    # 流程控制
    ask_count: int                          # 已追问次数（上限3）
    info_complete: bool                     # 信息是否完整
    force_generate: bool                    # 用户要求直接生成（"就这样吧"）

    # 输出
    itinerary: dict | None                  # 最终行程 JSON
```

---

## 3. 图结构

```
                    ┌─────────────────┐
          ┌────────│     __start__    │────────┐
          │        └─────────────────┘        │
          ↓                                   ↓
  ┌───────────────┐                   ┌───────────────┐
  │  intent_node   │                   │  chat_node     │
  │  (意图识别)     │                   │  (闲聊回复)     │
  └───────┬───────┘                   └───────────────┘
          │
          ↓
  ┌───────────────┐
  │  modify_node   │ ← 修改已有行程
  └───────┬───────┘
          │
          ↓
  ┌───────────────┐
  │ check_node     │ ← Python: 检查字段完整性
  └───────┬───────┘
          │
     ┌────┴────┐
     ↓         ↓
 完整/强制   不完整
     ↓         ↓
┌────────┐ ┌────────┐
│generate │ │ ask    │
│_node    │ │_node   │
│(LLM+Tool)│ │(LLM)  │
└────┬───┘ └────┬───┘
     ↓          ↓
  __end__    等用户下一轮输入 → 回到 __start__
```

### 路由逻辑

```python
def after_intent(state) -> str:
    if state["intent"] == "chat":
        return "chat_node"
    return "check_node"

def after_check(state) -> str:
    if state["info_complete"] or state["force_generate"] or state["ask_count"] >= 3:
        return "generate_node"
    return "ask_node"
```

---

## 4. 节点定义

### 4.1 意图识别节点（intent_node）

**输入**：用户最新消息 + 已有结构化字段
**输出**：intent + 更新后的结构化字段

```python
INTENT_PROMPT = """
你是行程规划助手的意图识别模块。

当前已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

用户最新消息：{message}

请返回 JSON：
{{
  "intent": "plan" | "modify" | "chat",
  "location": "更新后的位置，没有则保持原值",
  "budget": 更新后的预算（int）,
  "preferences": ["更新后的偏好列表"],
  "people_count": 更新后的人数（int）,
  "time_slot": "更新后的时间段",
  "force_generate": true/false（用户是否要求直接生成，如"就这样吧"/"不用问了"）
}}

规则：
- 只更新用户这次提到的字段，没提到的保持原值
- 用户说"就这样"/"随便"/"不用问了"时 force_generate=true
- 闲聊（天气、笑话等）时 intent="chat"
- 修改已有行程时 intent="modify"
"""
```

### 4.2 完整性检查节点（check_node）

**纯 Python，不调用 LLM**

```python
def check_node(state: PlannerState) -> dict:
    required = ["location", "time_slot"]
    optional_important = ["budget", "preferences"]

    has_required = all(state.get(f) for f in required)
    has_optional = any(state.get(f) for f in optional_important)

    return {
        "info_complete": has_required and has_optional,
        "turn_number": state.get("turn_number", 0) + 1,
    }
```

### 4.3 追问节点（ask_node）

**LLM 调用，生成自然语言追问**

```python
ASK_PROMPT = """
你是行程规划助手，现在需要向用户确认一些信息。

已知信息：
- 位置：{location}
- 预算：{budget}
- 偏好：{preferences}
- 人数：{people_count}
- 时间：{time_slot}

缺失信息：{missing_fields}

请用自然友好的方式，一次性询问缺失的关键信息（最多问2个问题）。
要求：口语化、简短、有emoji。
"""
```

### 4.4 生成行程节点（generate_node）

**LLM + Tools，ReAct 模式**

```python
GENERATE_PROMPT = """
你是行程规划助手，现在需要为用户生成一份周末行程。

用户信息：
- 位置：{location}
- 预算：{budget} 元
- 偏好：{preferences}
- 人数：{people_count} 人
- 时间：{time_slot}

请使用可用工具搜索合适的地点，然后生成行程方案。

输出要求：返回 JSON 格式的行程，包含 blocks 和 connections。
每个 block 包含：id, type, icon, name, duration, price, recommendation, address
每个 connection 包含：from, to, distance, time
"""
```

**绑定工具：**

```python
tools = [search_poi, get_social_reviews]  # 后续注册
llm_with_tools = llm.bind_tools(tools)
```

### 4.5 闲聊节点（chat_node）

**LLM 调用，直接回复，不进入行程流程**

```python
CHAT_PROMPT = """
你是"周末去哪儿"AI行程规划助手。
用户在闲聊，请简短友好地回复，并引导用户描述出行需求。
"""
```

### 4.6 修改节点（modify_node）

**LLM 调用，基于现有行程做局部调整**

```python
MODIFY_PROMPT = """
用户想修改现有行程。

当前行程：{current_itinerary}
用户修改要求：{message}

请只修改用户提到的部分，保持其他内容不变，返回完整的更新后行程。
"""
```

---

## 5. 上下文管理

### 5.1 优先级定义

| 优先级 | 类型 | 说明 |
|--------|------|------|
| 100 | system_prompt | 系统提示词，永远保留 |
| 100 | field_summary | 结构化字段摘要，永远保留 |
| 90 | user_input | 用户输入 |
| 80 | tool_output | 工具返回（POI、社媒数据） |
| 70 | itinerary | 行程结果 |
| 60 | ai_summary | AI 的摘要/确认 |
| 40 | ai_detail | AI 的详细解释 |
| 20 | ai_chitchat | AI 的闲聊/寒暄 |

### 5.2 裁剪策略

```python
TOKEN_BUDGET = 4000      # 给历史消息的 token 预算
PROTECT_RECENT = 3       # 最近 N 轮强制保留

def build_context(state: PlannerState) -> list[BaseMessage]:
    all_meta: list[MessageMeta] = []

    # 1. 永远保留的部分
    all_meta.append(MessageMeta(
        SystemMessage(content=SYSTEM_PROMPT),
        priority=100, token_count=estimate_tokens(SYSTEM_PROMPT)
    ))
    all_meta.append(MessageMeta(
        SystemMessage(content=build_field_summary(state)),
        priority=100, token_count=estimate_tokens(build_field_summary(state))
    ))

    # 2. 历史消息标注优先级
    for msg in state["messages"]:
        priority = classify_message(msg)
        all_meta.append(MessageMeta(
            message=msg,
            priority=priority,
            token_count=estimate_tokens(msg.content)
        ))

    # 3. 裁剪
    kept = trim_by_priority(all_meta, TOKEN_BUDGET, PROTECT_RECENT)

    return [m.message for m in kept]

def classify_message(msg: BaseMessage) -> int:
    if msg.type == "human":
        return 90   # user_input
    elif msg.type == "tool":
        return 80   # tool_output
    elif msg.type == "ai":
        content = msg.content
        if len(content) < 50:
            return 60   # ai_summary
        elif "```" in content or len(content) > 500:
            return 40   # ai_detail
        else:
            return 20   # ai_chitchat
    return 50

def trim_by_priority(meta_list, budget, protect_recent):
    # 分离受保护的最近N轮
    recent = []
    older = []
    turn_count = 0
    for m in reversed(meta_list):
        if m.message.type == "system":
            older.insert(0, m)
            continue
        if turn_count < protect_recent:
            recent.insert(0, m)
            turn_count += 1
        else:
            older.insert(0, m)

    # 计算已占用的 token
    recent_tokens = sum(m.token_count for m in recent)
    system_tokens = sum(m.token_count for m in older if m.priority == 100)
    remaining = budget - recent_tokens - system_tokens

    # 对 older 按优先级升序排列，从低优先级开始裁
    older.sort(key=lambda m: m.priority)
    kept_older = []
    used = 0
    for m in older:
        if m.priority == 100:
            kept_older.append(m)
            continue
        if used + m.token_count <= remaining:
            kept_older.append(m)
            used += m.token_count

    # 合并并按时间排序
    result = kept_older + recent
    return result
```

### 5.3 结构化字段摘要

```python
def build_field_summary(state: PlannerState) -> str:
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
    return "已提取信息：" + "，".join(parts) if parts else "尚未提取到任何信息"
```

---

## 6. Checkpoint 机制

### 6.1 存储选择

| 阶段 | 存储 | 说明 |
|------|------|------|
| 开发调试 | MemorySaver | 内存存储，重启丢失 |
| 生产环境 | SqliteSaver | 持久化到文件 |

### 6.2 使用方式

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)

# 每次调用传入 thread_id
config = {"configurable": {"thread_id": "user_abc_session_1"}}
result = graph.invoke(input_data, config=config)
```

### 6.3 多窗口隔离

```
thread_id = "{user_id}_{session_id}"

示例：
- user123_session_1  → 用户123的第1个对话
- user123_session_2  → 用户123的第2个对话（独立状态）
```

前端负责生成和管理 thread_id，后端所有操作都通过 thread_id 路由到对应状态。

---

## 7. 工具注册（后续扩展）

### 7.1 工具接口规范

```python
from langchain_core.tools import tool

@tool
def search_poi(keyword: str, location: str, radius: int = 3000) -> list[dict]:
    """搜索指定位置附近的兴趣点（餐厅、咖啡店、景点等）"""
    # 调用地图 API
    ...

@tool
def get_social_reviews(poi_name: str, location: str) -> str:
    """获取某个地点的社交媒体评价和推荐理由"""
    # 搜索引擎聚合 + 本地知识库
    ...
```

### 7.2 注册方式

```python
# 在 generate_node 中绑定
tools = [search_poi, get_social_reviews]
llm_with_tools = llm.bind_tools(tools)
```

### 7.3 扩展点

后续可注册的工具：
- `get_weather` — 天气查询
- `get_traffic` — 实时路况
- `get_opening_hours` — 营业时间查询
- `book_restaurant` — 餐厅预订（需要授权）

---

## 8. 完整调用流程示例

```
用户第1轮："周六下午带女朋友出去玩"
  → intent_node: intent=plan, time_slot="周六下午", people_count=2
  → check_node: location=None, budget=None → info_complete=false
  → ask_node: "你们在哪个城市呀？预算大概多少？"

用户第2轮："在杭州西湖，预算300"
  → intent_node: location="杭州西湖", budget=300
  → check_node: info_complete=true（有位置+预算+人数+时间）
  → generate_node: LLM调用search_poi工具 → 生成行程JSON
  → 返回行程卡片

用户第3轮："帮我换个餐厅"
  → intent_node: intent=modify
  → modify_node: 基于现有行程替换餐厅部分
  → 返回更新后的行程

用户第4轮："今天天气怎么样"
  → intent_node: intent=chat
  → chat_node: 直接回复天气，引导回行程话题
```
