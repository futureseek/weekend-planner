# Roam 漫游 · 本地智能路线规划系统

Roam 漫游是基于 `futureseek/weekend-planner` 的本地智能路线规划项目。项目目标是让用户输入本地出行条件和偏好后，系统结合 POI 数据、评价/攻略信号、时间窗、预算、人数和转场成本，生成可以直接执行的多方案路线。

当前版本对照上游 `futureseek/weekend-planner` 的 `feature/route-planner` 最新提交 `909b5d1 feat: Phase 1 MVP - 路线优化器改造 + 调整按钮走Agent管线` 继续扩展：保留“聊天生成路线 + 右侧路线工作台 + Agent 调整按钮”的基础，同时加入 Roam 品牌、结构化本地路线条件、多日拆分、多风格方案、近期热门活动、起点检索、地图草图和中英文 UI。

## 项目定位

用户在出行或游玩时，通常需要把多个目的地串联成路线，同时权衡时间、预算、排队、餐饮质量、同行人群和交通转场。Roam 希望把这些决策前置到本地规划系统中：

- 用户先填写城市、区县、日期、时间、预算、人数和起点。
- 用户只在偏好框中写“想吃顿好的、少排队、想看展、喜欢爬山、想打游戏、不想太累”等自然偏好。
- 系统检索本地 POI、参考攻略/活动信号，生成多个可切换方案。
- 方案在右侧展示为路线草图和当天执行清单，支持继续要求“少走路 / 性价比 / 少排队 / 换餐厅”。

## 当前状态

### 已实现

- **结构化本地路线条件**：前端将城市、区县、起点、日期、时间、预算、人数拆成独立输入项，偏好只保留自然语言描述。
- **全国 POI 检索**：优先使用高德 Web 服务检索 POI，SQLite 作为缓存和兜底数据；支持城市、区县和起点附近的数据召回。
- **起点候选搜索**：`/api/location/geocode` 聚合高德 inputtips、POI 搜索和地理编码，优先返回真实 POI，降低行政区误匹配。
- **多日路线生成**：可按日期范围生成 Day 1 / Day 2 / Day N 的行程拆分。
- **多方案输出**：默认生成综合推荐、少走路、吃好玩好、省钱轻量等不同风格方案。
- **预算和时间策略**：按人数和预算估算总花费，按时间窗控制可用时长、站点数量和餐饮/娱乐时段。
- **人群与偏好策略**：对美食、咖啡、购物、看展、自然、夜景、爬山、游戏、亲子、少排队、放松等偏好做路线倾向调整。
- **近期热门活动**：通过公开搜索信号获取出行时间范围内的活动参考，默认偏向年轻用户更关心的演出、展览、市集、livehouse、动漫/游戏等内容。
- **UGC/攻略信号**：支持公开搜索小红书/攻略类内容，也支持读取无需登录和验证码的公开网页。
- **右侧路线工作台**：展示方案指标、方案切换、日期切换、路线草图、执行清单和快速调整按钮。
- **动态调整**：`/api/itinerary/adjust` 将“少走路 / 少排队 / 省钱 / 换餐厅”等动作重新送入 Agent 管线。
- **Markdown 回复**：AI 回复支持 Markdown 渲染。
- **中英文 UI 基础适配**：页面支持中英文切换，英文模式下主要 UI 文案切换为英文。
- **模型路由雏形**：配置支持 `fast_agent`、`parser_agent`、`chat_agent`、`explain_agent`、`guide_agent` 等角色，便于把轻任务拆给更快或更低成本的模型。

### 待修与待优化

这些问题是当前版本明确保留的开发事项：

- **起点功能仍需完善**：当前已支持候选检索和定位起点，但“当前位置授权、文字搜索、起点到第一个目的地的真实交通接入、起点长期状态管理”仍需继续打磨。
- **地图展示未完善**：当前更偏路线草图/展示用途；真实地图瓦片、可拖动地图、标点详情面板、按交通方式绘制真实道路/地铁/公交路径仍需继续优化。
- **方案生成仍需优化**：预算利用、时间匹配、站点密度、餐饮与娱乐比例、偏好匹配、活动接入质量仍需要更多测试和规则/模型协同优化。
- **热门活动链接质量需要持续过滤**：需要进一步排除无效链接、泛化页面、过期活动和来源质量较低的结果。
- **Agent 响应速度仍需优化**：复杂规划可能耗时较长，建议接入快模型承担解析、检索摘要、闲聊和轻量判断任务。
- **英文适配未完全覆盖业务语义**：UI 基础文案已切换，但英文路线生成、英文搜索策略和英文活动摘要仍需继续增强。

## 技术栈

### 前端

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- dnd-kit

### 后端

- Python 3.13+
- Flask
- Flask-CORS
- LangGraph
- LangChain / LangChain OpenAI
- SQLite
- 高德地图 Web 服务
- Tavily 搜索，可选

## 项目结构

```text
weekend-planner/
├── backend/
│   ├── agent/                 # LangGraph Agent 节点、状态和上下文
│   ├── db/                    # SQLite 初始化和种子数据
│   ├── services/              # POI、路线优化、活动、评价、攻略等服务
│   ├── tools/                 # 高德、Tavily、公开网页/UGC 工具
│   ├── app.py                 # Flask API 入口
│   ├── chat_service.py        # 对话服务封装
│   ├── config.py              # 配置加载和模型路由
│   └── pyproject.toml
├── frontend/
│   ├── app/                   # Next.js App Router
│   ├── components/
│   │   ├── Chat.tsx           # 左侧对话和本地路线条件输入
│   │   ├── Canvas.tsx         # 右侧路线工作台和地图草图
│   │   └── MarkdownMessage.tsx
│   ├── lib/api.ts             # 前端 API 封装
│   └── package.json
├── config/
│   └── api_config.json        # 本地 API Key 和模型配置，不应提交
├── data/                      # SQLite POI 缓存
└── README.md
```

## 配置流程

### 1. 准备环境

需要安装：

- Python 3.13+
- uv
- Node.js 18+，建议 Node.js 20+
- npm
- 高德地图 Web 服务 Key
- 一个 OpenAI 兼容格式的模型 API
- Tavily Key，可选，用于公开搜索和热门活动/攻略信号

### 2. 配置后端 API Key

在项目根目录创建或编辑：

```text
config/api_config.json
```

最小配置：

```json
{
  "amap_key": "高德地图 Web 服务 Key",
  "tavily_key": "",
  "model": {
    "qa_agent": {
      "model_name": "模型名称",
      "api_key": "模型 API Key",
      "base_url": "OpenAI 兼容接口地址",
      "temperature": 0.2,
      "timeout": 45,
      "max_retries": 1,
      "reasoning_effort": "low"
    }
  }
}
```

推荐配置，适合后续加速 Agent：

```json
{
  "amap_key": "高德地图 Web 服务 Key",
  "tavily_key": "Tavily Key，可选",
  "model": {
    "qa_agent": {
      "model_name": "质量较高的主模型",
      "api_key": "主模型 API Key",
      "base_url": "OpenAI 兼容接口地址",
      "temperature": 0.2,
      "timeout": 45,
      "max_retries": 1,
      "reasoning_effort": "low"
    },
    "fast_agent": {
      "model_name": "较快较便宜的模型，如 qwen-turbo / qwen3-instruct / deepseek-chat",
      "api_key": "可选；不填则复用 qa_agent",
      "base_url": "可选；不填则复用 qa_agent"
    },
    "parser_agent": {
      "model_name": "结构化解析模型，可复用 fast_agent"
    },
    "chat_agent": {
      "model_name": "闲聊和追问模型，可复用 fast_agent"
    },
    "explain_agent": {
      "model_name": "最终解释模型，可复用 qa_agent"
    },
    "guide_agent": {
      "model_name": "攻略和活动摘要模型，可复用 fast_agent"
    }
  }
}
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `amap_key` | 是 | 高德地图 Web 服务 Key，用于 POI、行政区、地理编码、逆地理编码和路线数据。 |
| `tavily_key` | 否 | Tavily 搜索 Key，用于公开网页、活动和攻略信号。为空时相关功能会降级。 |
| `model.qa_agent` | 是 | 主模型配置，必须支持 OpenAI 兼容接口。 |
| `model.fast_agent` | 否 | 快速模型，适合意图识别、轻量解析、活动摘要等低成本任务。 |
| `model.parser_agent` | 否 | 结构化解析模型，默认复用 `fast_agent`。 |
| `model.chat_agent` | 否 | 闲聊/追问模型，默认复用 `fast_agent`。 |
| `model.explain_agent` | 否 | 最终路线解释模型，默认复用 `qa_agent`。 |
| `model.guide_agent` | 否 | 攻略和热门活动摘要模型，默认复用 `fast_agent`。 |

### 3. 配置前端 API 地址，可选

前端默认请求：

```text
http://127.0.0.1:5000
```

如需修改，创建 `frontend/.env.local`：

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:5000
```

## 启动项目

### 后端

```bash
cd backend
uv sync
uv run python app.py
```

默认端口：

```text
http://127.0.0.1:5000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认端口：

```text
http://localhost:3000
```

如果 3000 端口被占用，Next.js 会自动切换到 3001。若希望固定使用 3000，请先关闭占用 3000 的本地进程。

## 使用流程

1. 打开前端页面。
2. 在“本地路线条件”中填写城市。
3. 点击“查区”加载该城市的区县，选择一个或多个考虑区县。
4. 填写起点，可以输入地点名并从候选中选择，也可以尝试定位起点。
5. 选择出行日期、时间范围。
6. 填写预算和人数。
7. 在偏好框中只写偏好、爱好和避雷点。
8. 点击“生成路线”。
9. 在右侧路线工作台切换方案和日期，查看路线草图与执行清单。
10. 可点击底部快速调整按钮继续优化方案。

示例偏好：

```text
想吃顿好的，然后放松一下，少排队，不想太累
```

```text
喜欢爬山和咖啡，下午想轻松点
```

```text
想打游戏、逛街、吃火锅，预算别超
```

## API 接口说明

### GET /api/health

健康检查。

响应：

```json
{
  "status": "ok"
}
```

### POST /api/chat

主对话接口。用于生成路线、继续追问或发起修改。

请求：

```json
{
  "message": "【结构化本地路线需求】\n城市：广州\n考虑区县：天河区、番禺区\n起点：中山大学\n出行日期：6月3日-6月3日\n时间：18:30-22:00\n预算：300元\n人数：1人\n偏好与爱好：想吃顿好的，然后放松一下",
  "session_id": "default"
}
```

响应：

```json
{
  "reply": "Markdown 格式的路线说明",
  "itinerary": {
    "plan_name": "综合推荐",
    "blocks": [],
    "connections": [],
    "days": [],
    "total_duration": 203,
    "total_price": 280,
    "total_distance": 900,
    "alternatives": []
  },
  "alternatives": [],
  "intent": "plan"
}
```

### POST /api/chat/stream

伪流式对话接口。当前实现是先生成完整结果，再按小片段返回文本。

请求同 `/api/chat`。

响应类型：

```text
text/event-stream
```

### POST /api/reorder

按前端拖拽后的 block 顺序重新计算连接信息。

请求：

```json
{
  "session_id": "default",
  "blocks": [
    {
      "id": "poi_1",
      "name": "地点 A",
      "duration": 60,
      "price": 50
    },
    {
      "id": "poi_2",
      "name": "地点 B",
      "duration": 45,
      "price": 30
    }
  ]
}
```

响应：

```json
{
  "reply": "已按新顺序重新规划行程！",
  "itinerary": {
    "blocks": [],
    "connections": [],
    "total_duration": 105,
    "total_price": 80
  }
}
```

### POST /api/itinerary/adjust

路线快速调整接口。当前会把按钮动作转换成自然语言，并重新走 Agent 规划管线。

请求：

```json
{
  "session_id": "default",
  "action": "less_walking",
  "payload": {}
}
```

支持的常用动作：

| action | 含义 |
| --- | --- |
| `less_walking` | 少走路，优先选近一点的地点。 |
| `less_queue` | 少排队，避开排队风险高的地点。 |
| `lower_budget` | 省钱，降低预算重新规划。 |
| `replace_poi` | 替换某类地点，例如餐厅。 |

响应：

```json
{
  "message": "转换后的自然语言修改请求",
  "reply": "Markdown 格式说明",
  "itinerary": {},
  "alternatives": []
}
```

### POST /api/location/reverse

逆地理编码。把经纬度转成省市区和地址。

请求：

```json
{
  "location": "113.264385,23.129112"
}
```

响应：

```json
{
  "formatted_address": "广东省广州市越秀区...",
  "province": "广东省",
  "city": "广州市",
  "district": "越秀区",
  "township": "",
  "adcode": "440104",
  "location": "113.264385,23.129112"
}
```

### POST /api/location/geocode

起点/地点候选搜索。聚合高德 inputtips、POI 搜索和地理编码，适合前端“起点”输入框。

请求：

```json
{
  "address": "中山大学",
  "city": "广州"
}
```

响应：

```json
{
  "items": [
    {
      "name": "中山大学",
      "formatted_address": "广东省广州市海珠区 中山大学",
      "address": "",
      "city": "广州",
      "district": "广东省广州市海珠区",
      "adcode": "440105",
      "location": "113.303943,23.094742",
      "level": "POI",
      "source": "tip"
    }
  ]
}
```

### POST /api/location/districts

查询城市下的区县。

请求：

```json
{
  "city": "广州"
}
```

响应：

```json
{
  "city": "广州",
  "districts": [
    {
      "name": "天河区",
      "adcode": "440106",
      "center": "113.361597,23.124817",
      "level": "district"
    }
  ]
}
```

### POST /api/ugc/xhs/search

公开搜索小红书/攻略类信号。注意：该接口不绕过登录、验证码或反爬限制，只使用公开搜索结果。

请求：

```json
{
  "query": "广州 livehouse 小红书 6月",
  "limit": 5
}
```

响应：

```json
{
  "items": [
    {
      "title": "搜索结果标题",
      "url": "https://...",
      "content": "摘要"
    }
  ]
}
```

### POST /api/ugc/read-page

读取公开网页文本。只适合无需登录和验证码的页面。

请求：

```json
{
  "url": "https://example.com",
  "max_chars": 4000
}
```

响应：

```json
{
  "url": "https://example.com",
  "title": "页面标题",
  "content": "可见正文文本"
}
```

## 后端 Agent 流程

当前后端核心流程在 `backend/agent/nodes.py` 和 `backend/agent/graph.py` 中：

```text
intent
  -> check
  -> ask / chat / collect_data
  -> rank_poi
  -> optimize_route
  -> explain
```

各阶段职责：

- `intent`：识别规划、修改、闲聊，提取城市、预算、人数、日期、时间、偏好、起点等约束。
- `check`：检查必要信息是否完整。
- `ask`：信息不足时追问。
- `collect_data`：按城市、区县、偏好和活动信号收集 POI。
- `rank_poi`：结合偏好、预算、人群和评价线索筛选候选 POI。
- `optimize_route`：生成多方案、多日拆分、时间安排、连接信息和总指标。
- `explain`：生成 Markdown 说明，并输出近期热门活动参考。

## 前端展示逻辑

- 左侧是对话和本地路线条件表单。
- 右侧是路线工作台。
- 生成路线后，右侧展示：
  - 方案指标：总时长、预计花费、转场距离。
  - 方案切换：综合推荐、少走路、吃好玩好、省钱轻量等。
  - 日期切换：多日时显示 Day 1 / Day 2 / Day N。
  - 路线草图：按地点顺序绘制数字标点和连接线。
  - 执行清单：按时间展示每个地点、停留时长、费用、类型、转场说明。
  - 快速调整：少走路、性价比、少排队、换餐厅。

## 数据与外部服务说明

### 高德地图

使用场景：

- POI 搜索
- 输入联想
- 地理编码
- 逆地理编码
- 行政区查询
- 部分路线距离/时间计算

当前地图展示仍未完整接入真实地图交互，更多是使用坐标和连接线做路线草图。

### SQLite

使用场景：

- 缓存已检索 POI
- 保存少量种子 POI
- 为无网络或接口异常时提供兜底

### Tavily / 公开网页

使用场景：

- 近期热门活动参考
- 攻略/UGC 搜索摘要
- 公开网页正文读取

不会绕过登录、验证码、付费墙或站点反爬限制。

## 开发检查命令

后端语法检查：

```bash
uv run python -m compileall -q backend
```

前端 TypeScript 检查：

```bash
cd frontend
npx.cmd tsc --noEmit --incremental false
```

前端构建：

```bash
cd frontend
npm run build
```

## 与上游 feature/route-planner 的主要差异

上游 `feature/route-planner` 最新提交 `909b5d1` 的 README 主要描述：

- 周末去哪儿 AI 行程规划助手。
- 前端为 Next.js + Tailwind + dnd-kit。
- 后端为 Flask + LangGraph。
- 支持 `/api/chat` 生成可拖拽行程图块。
- Phase 1 已加入路线优化器和调整按钮 Agent 管线。

当前 Roam 版本在此基础上增加：

- 产品名从“周末去哪儿”调整为 **Roam 漫游**。
- 输入方式从纯聊天扩展为“结构化本地路线条件 + 偏好输入框”。
- 新增城市区县选择、起点检索、定位起点、多日日期范围、时间范围、预算和人数输入。
- 新增 POI-first 起点搜索和全国行政区/POI 支持。
- 新增多日、多方案、预算利用、时间匹配和人群偏好策略。
- 新增近期热门活动、UGC/攻略搜索和公开页面读取。
- 新增中英文 UI 切换。
- 新增路线草图、执行清单、方案切换和日期切换。
- 增强模型配置，支持多角色模型路由。

## 后续优先级建议

1. **修起点链路**：把起点候选、当前位置、起点到首站交通和展示逻辑彻底统一。
2. **升级地图展示**：先保证数字标点、路线顺序和连接方式正确，再考虑真实地图、可拖拽、标点详情和道路/地铁路径。
3. **提高方案质量**：强化预算利用、餐饮时段、夜景时段、娱乐密度、非餐饮比例和偏好命中率。
4. **优化 Agent 耗时**：拆分轻任务模型，缓存 POI/活动结果，减少不必要的 LLM 调用。
5. **提高热门活动质量**：按出行日期窗口过滤，保留可点击链接，排除泛化页面和过期内容。
6. **完善英文模式**：不仅翻译 UI，也让搜索策略、活动摘要和最终路线说明适配英文用户。

