# Roam 漫游

Roam 是一个本地智能路线规划系统。用户先给出城市、区县、起点、日期、时间窗、预算、人数和偏好，系统结合高德 POI/地理编码/公交换乘、本地 POI 数据、公开攻略信号和路线优化策略，生成多种可执行的本地出行方案。

项目目标不是做通用聊天旅游助手，而是围绕“多个目的地如何串成一条能走、预算和时间都合理、符合个人偏好”的路线规划问题，降低用户反复搜索、筛选和组合的成本。

## 已实现能力

- 结构化出行输入：城市、区县、起点、出行日期、时间、预算、人数、偏好分开填写，减少大模型误解析。
- 全国城市/区县支持：优先调用高德行政区接口，失败时使用本地兜底区县表。
- 起点与地点检索：支持高德输入提示、POI 搜索和地理编码合并排序，用于起点和目的地匹配。
- 多来源 POI：结合高德 POI、本地 SQLite 种子数据、公开攻略/UGC 信号补充候选点。
- 多方案生成：默认生成综合推荐、少走路、吃好玩好、省钱轻量等不同风格方案。
- 预算控制：路线优化阶段会按预算约束筛选和裁剪，测试要求方案总价不超过用户预算。
- 时间策略：按出行时间窗安排正餐、下午茶、夜景、娱乐等活动，避免把夜景放到上午、早茶放到下午。
- 路线密度：单日路线在时间允许时尽量保留至少 4 个有效行动点，避免只有 1-2 个点。
- 起点接入：方案会计算起点到第一个目的地的转场时间和方式，并在路线面板展示。
- 交通方式修正：长距离步行会尝试切换为公共交通；公共交通节点可展示换乘说明。
- POI 噪声过滤：过滤人民政府、养老服务中心、办公机构、不对外开放等明显不适合游玩的地点。
- 快速调整：支持少走路、性价比、少排队、换餐厅等局部调整，并把调整结果重新加载到右侧方案面板。
- 前端体验：支持中英文切换、Markdown 回答渲染、结构化表单、偏好卡片、路线面板、路线地图预览和执行清单。

## 项目结构

```text
weekend-planner/
├── backend/
│   ├── app.py                  # Flask API 入口
│   ├── chat_service.py         # 会话、路线生成和快速调整服务
│   ├── config.py               # 配置读取和多模型配置合并
│   ├── agent/                  # LangGraph 路线规划节点
│   ├── services/               # POI、活动/攻略、路线优化服务
│   ├── tools/                  # 高德、Tavily、公开网页/小红书辅助工具
│   ├── db/                     # SQLite 初始化和种子数据
│   └── tests/                  # pytest 测试
├── frontend/
│   ├── app/                    # Next.js App Router
│   ├── components/             # Chat、Canvas、Markdown 渲染组件
│   └── lib/api.ts              # 前端 API 封装
└── config/
    └── api_config.json         # 本地密钥与模型配置，不应提交真实 key
```

## 配置

后端读取 `config/api_config.json`。建议保留真实密钥在本地，提交前确认没有泄露。

```json
{
  "amap": {
    "api_key": "YOUR_AMAP_WEB_SERVICE_KEY"
  },
  "tavily": {
    "api_key": "YOUR_TAVILY_KEY_OPTIONAL"
  },
  "model": {
    "fast_agent": {
      "api_key": "YOUR_QWEN_OR_COMPATIBLE_KEY",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model_name": "qwen-turbo-latest",
      "temperature": 0.2,
      "timeout": 20
    },
    "chat_agent": {
      "api_key": "YOUR_QWEN_OR_COMPATIBLE_KEY",
      "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "model_name": "qwen-plus-latest",
      "temperature": 0.35,
      "timeout": 45
    }
  }
}
```

前端可在 `frontend/.env.local` 配置：

```env
NEXT_PUBLIC_API_BASE=http://127.0.0.1:5000
NEXT_PUBLIC_AMAP_JS_KEY=YOUR_AMAP_JS_API_KEY
NEXT_PUBLIC_AMAP_SECURITY_JS_CODE=YOUR_AMAP_JS_SECURITY_CODE
```

说明：

- `amap.api_key` 用于后端 POI、地理编码、逆地理编码、行政区和公交换乘。
- `NEXT_PUBLIC_AMAP_JS_KEY` 和 `NEXT_PUBLIC_AMAP_SECURITY_JS_CODE` 用于前端高德 JS 能力。
- `fast_agent` 适合意图解析、快速调整、轻量判断。
- `chat_agent` 适合完整路线生成和解释。
- `tavily` 是公开攻略/网页信号的可选增强项。

## 启动

后端：

```bash
cd backend
uv sync
uv run python app.py
```

默认监听 `http://127.0.0.1:5000`。

前端：

```bash
cd frontend
npm install
npm run dev
```

默认访问 `http://localhost:3000`。

如果在 OneDrive 路径下遇到 Next.js `.next` 的 `EINVAL readlink` 报错，停止前端服务后删除 `frontend/.next`，再重新执行 `npm run dev`。

## 后端接口

| Method | Path | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/chat` | 生成路线或处理普通对话 |
| `POST` | `/api/chat/stream` | 流式聊天接口 |
| `POST` | `/api/reorder` | 对指定 POI 列表重新排序 |
| `POST` | `/api/itinerary/adjust` | 快速调整当前方案 |
| `POST` | `/api/location/reverse` | 经纬度逆地理编码，支持低精度定位保护 |
| `POST` | `/api/location/geocode` | 地点搜索，合并输入提示、POI 和地理编码 |
| `POST` | `/api/location/districts` | 获取城市区县 |
| `POST` | `/api/route/transit` | 查询公交/地铁换乘方案 |
| `POST` | `/api/ugc/xhs/search` | 公开攻略/小红书线索搜索 |
| `POST` | `/api/ugc/read-page` | 读取公开网页内容 |

### `/api/chat`

请求：

```json
{
  "session_id": "demo-session",
  "message": "城市：广州\n考虑区县：番禺区\n起点：中山大学广州校区东校园\n出行日期：6月8日-6月8日\n时间：10:30-22:00\n预算：300元\n人数：1人\n偏好与爱好：想吃顿好的，晚上看夜景，少排队"
}
```

响应会返回可读回答，并在 `plan` 字段中返回结构化路线：

```json
{
  "message": "...",
  "plan": {
    "title": "综合推荐",
    "days": [],
    "options": []
  }
}
```

### `/api/location/geocode`

请求：

```json
{
  "city": "广州",
  "keyword": "中山大学广州校区东校园"
}
```

用于起点搜索和地点匹配。

### `/api/itinerary/adjust`

请求：

```json
{
  "session_id": "demo-session",
  "mode": "swap_food"
}
```

支持快速调整当前会话中的路线方案，例如少走路、性价比、少排队、换餐厅。

### `/api/route/transit`

请求：

```json
{
  "city": "广州",
  "origin": "113.390521,23.065606",
  "destination": "113.361597,23.124817"
}
```

返回公交/地铁换乘摘要和步骤，用于路线面板中的交通详情。

## 测试

后端：

```bash
cd backend
uv run pytest
```

前端类型检查：

```bash
cd frontend
npx tsc --noEmit --incremental false
```

当前测试重点覆盖：

- 健康检查和基础接口
- 区县兜底、地理编码、逆地理编码
- 起点接入和首段转场
- POI 噪声过滤
- 路线不少于合理行动点
- 多方案差异化
- 长步行切换公共交通
- 预算不超出
- 快速调整和换餐厅逻辑

## 已知限制

- 地图展示仍偏路线预览，不是完整导航地图；真实道路级 polyline、站点级换乘和地图交互仍需继续增强。
- 浏览器/IP 定位精度可能很差，精确起点建议用户手动输入并从搜索结果中选择。
- 小红书等 UGC 来源存在反爬和登录限制，目前只能利用公开搜索结果和可访问页面。
- 多区县同时选择会显著扩大 POI 搜索空间，建议优先选 1 个区县，最多 2 个相邻区县。
- 方案质量依赖 POI 数据覆盖、API Key 可用性和模型响应质量。

## 后续计划

- 接入更完整的高德地图 JS 展示，支持真实底图、方案标点、道路/地铁线路和可点击详情。
- 强化 UGC/攻略信号缓存，把热门收藏路线、宝藏小店、适龄活动纳入排序。
- 优化多模型调度，把解析、搜索、排序、解释拆成更快的轻量任务。
- 提升英文版覆盖率，让表单、路线面板、AI 回答和调整结果统一切换。
- 支持用户手动替换 POI、锁定地点、拖拽重排并重新计算交通和预算。
