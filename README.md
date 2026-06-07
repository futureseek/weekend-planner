# Roam 漫游

Roam 是一个本地智能路线规划系统。用户选择城市、区县、日期、时间、起点、预算和人数后，只需补充偏好与避雷点，系统会结合高德 POI、评价/攻略信号、时间窗、预算策略和转场距离，生成多风格、可执行的本地多目的地路线。

当前版本基于 `futureseek/weekend-planner` 的 `feature/route-planner` 继续升级，重点从「一句话聊天 Demo」改为「结构化本地路线规划工作台」。

## 已实现

- 结构化条件输入：城市、区县、起点、日期范围、时间范围、预算、人数独立填写，偏好保留自然语言。
- 全国 POI 检索：优先调用高德 Web 服务，SQLite 种子数据兜底。
- 起点定位：前端可优先使用高德 JS API 高精度定位；后端只接受精度足够的坐标，并查找 20m 内最近 POI/道路/AOI 作为公共交通起点锚点。
- 起点搜索：支持文字搜索起点，合并高德输入提示、POI 搜索和地理编码结果。
- 多方案路线：综合推荐、少走路、吃好玩好、省钱轻量等方案可切换。
- 多日拆分：按日期范围生成 Day 1 / Day 2 / Day N。
- 个性化策略：支持美食、咖啡、购物、看展、夜景、爬山、户外、游戏、亲子、少排队、放松等偏好。
- 预算与时间策略：按人数估算花费，控制正餐、咖啡、娱乐、夜景等项目的合理时段。
- 公交转场详情：公共交通转场会尝试调用高德公交换乘接口，前端可展开查看线路摘要。
- 路线展示：右侧显示路线草图、执行清单、周边 POI、地点详情和快速调整。
- 升级建议：基于用户画像和本地 POI 给出可追加预算的体验建议。
- 中英文界面：顶部支持中英文切换。
- 多模型路由：支持 `qa`、`fast`、`parser`、`chat`、`explain`、`guide` 分角色配置。

## 待优化

- 地图仍是路线草图，不是真实可导航地图。
- 真实道路/地铁 polyline 渲染需要后续接入高德 JS API 或更完整的路线规划接口。
- 起点搜索排序、POI 质量和多城市回归仍需继续打磨。
- 小红书等 UGC 数据目前只能通过公开搜索信号辅助，不能稳定获取完整内容。

## 技术栈

- 前端：Next.js 14、React 18、TypeScript、Tailwind CSS
- 后端：Python 3.13+、Flask、LangGraph、LangChain、SQLite
- 数据：高德地图 Web 服务、公开网页/UGC 工具、本地种子 POI
- 模型：OpenAI 兼容接口，当前推荐 DashScope Qwen 兼容模式

## 目录结构

```text
weekend-planner/
├── backend/
│   ├── agent/              # LangGraph 节点、状态、提示词
│   ├── services/           # POI、路线优化、评价、攻略服务
│   ├── tools/              # 高德、UGC、网页工具
│   ├── tests/              # pytest
│   ├── app.py              # Flask API
│   └── config.py           # 配置和模型路由
├── frontend/
│   ├── app/
│   ├── components/         # Chat、Canvas、Markdown 渲染
│   └── lib/api.ts
├── config/api_config.json  # 本地密钥配置，不提交
└── README.md
```

## 配置

创建 `config/api_config.json`：

```json
{
  "amap_key": "高德地图 Web 服务 Key",
  "tavily_key": "",
  "model": {
    "qa_agent": {
      "model_name": "qwen-plus",
      "api_key": "DashScope API Key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "temperature": 0.18,
      "timeout": 30,
      "max_retries": 1,
      "extra_body": { "enable_thinking": false }
    },
    "fast_agent": {
      "model_name": "qwen-turbo",
      "api_key": "DashScope API Key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "temperature": 0.1,
      "timeout": 15,
      "max_retries": 0,
      "extra_body": { "enable_thinking": false }
    },
    "parser_agent": {
      "model_name": "qwen-turbo",
      "api_key": "DashScope API Key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "temperature": 0,
      "timeout": 12,
      "max_retries": 0,
      "extra_body": { "enable_thinking": false }
    },
    "chat_agent": {
      "model_name": "qwen-turbo",
      "api_key": "DashScope API Key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "temperature": 0.2,
      "timeout": 12,
      "max_retries": 0,
      "extra_body": { "enable_thinking": false }
    },
    "explain_agent": {
      "model_name": "qwen-plus",
      "api_key": "DashScope API Key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "temperature": 0.2,
      "timeout": 25,
      "max_retries": 1,
      "extra_body": { "enable_thinking": false }
    },
    "guide_agent": {
      "model_name": "qwen-turbo",
      "api_key": "DashScope API Key",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "temperature": 0.15,
      "timeout": 15,
      "max_retries": 0,
      "extra_body": { "enable_thinking": false }
    }
  }
}
```

前端默认请求 `http://127.0.0.1:5000`。需要改后端地址时创建 `frontend/.env.local`：

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:5000
NEXT_PUBLIC_AMAP_JS_KEY=高德地图 JavaScript API Key
NEXT_PUBLIC_AMAP_SECURITY_JS_CODE=高德地图 JavaScript API 安全密钥
```

`NEXT_PUBLIC_AMAP_JS_KEY` 不是必填；未配置时会退回浏览器原生定位。但桌面端原生定位可能退化成低精度坐标，Roam 会拒绝写入低精度起点，建议配置高德 JS API Key。

## 启动

后端：

```bash
cd backend
uv sync
uv run python app.py
```

前端：

```bash
cd frontend
npm install
npm run dev
```

默认端口：

- 后端：`http://127.0.0.1:5000`
- 前端：`http://localhost:3000`

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/chat` | 主对话接口，生成路线或继续调整 |
| `POST` | `/api/itinerary/adjust` | 快速调整当前路线 |
| `POST` | `/api/reorder` | 手动重排后重新计算 |
| `POST` | `/api/location/reverse` | 浏览器坐标逆地理编码，并匹配 20m 内最近 POI 起点 |
| `POST` | `/api/location/geocode` | 起点/地点候选搜索 |
| `POST` | `/api/location/districts` | 城市区县列表 |
| `POST` | `/api/ugc/xhs/search` | 公开攻略搜索工具 |
| `POST` | `/api/ugc/read-page` | 公开网页读取工具 |

`/api/chat` 请求示例：

```json
{
  "session_id": "demo",
  "message": "城市：广州\n考虑区县：番禺区、天河区\n起点：113.390600,23.065610，广州番禺广场地铁站A口\n出行日期：6月5日-6月5日\n时间：17:00-22:00\n预算：500元\n人数：2人\n偏好与爱好：想吃顿好的，晚餐可以适当多花一点，优先评分高、有特色、排队可控的餐厅\n请生成最适合该条件的出行方案。"
}
```

响应核心字段：

```json
{
  "reply": "Markdown 文本",
  "itinerary": {
    "plan_name": "综合推荐",
    "blocks": [],
    "days": [],
    "map_pois": [],
    "upgrade_suggestions": [],
    "start_transfer": {}
  },
  "alternatives": [],
  "intent": "plan"
}
```

`/api/location/reverse` 返回示例：

```json
{
  "name": "广州番禺广场地铁站A口",
  "location": "113.390600,23.065610",
  "original_location": "113.390521,23.065606",
  "anchor_distance_m": 9,
  "city": "广州市",
  "district": "番禺区",
  "source": "nearest_poi_20m"
}
```

## 开发检查

后端：

```bash
cd backend
uv run pytest
uv run python -m compileall -q .
```

前端：

```bash
cd frontend
npx tsc --noEmit --incremental false
```

