# Roam 漫游

Roam 漫游是一个本地智能路线规划系统。用户用自然语言描述城市/区域、时间、人数、预算和偏好后，系统会结合高德 POI、本地缓存、评价标签、攻略信号和路线距离，生成可直接执行的多方案行程。英文版本中产品名统一为 Roam。

## 已实现能力

- 全国 POI 动态检索：优先调用高德 Web 服务，支持国内城市和区域；SQLite 只作为缓存和少量兜底数据。
- 多方案路线：默认生成综合推荐、少走路、吃好玩好、省钱轻量等不同风格方案。
- 预算与时间约束：按总预算和同行人数估算花费，按半天/一天/多日控制站点数量和转场成本。
- 个性化偏好：支持美食、咖啡、看展、自然、购物、夜景、历史、亲子、拍照、少排队等标签。
- 动态调整：生成后可继续要求少走路、省钱、少排队、换餐厅，并刷新右侧路线工作台。
- Markdown 渲染：助手回复支持标题、列表、加粗和行程摘要。
- 模型降级：模型用于复杂语义增强；规则解析和本地解释可在模型慢或临时异常时继续生成路线。
- UGC 增强：支持通过公开搜索摘要接入小红书/攻略类信号；不做验证码、登录墙或反爬绕过。

## 项目结构

```text
weekend-planner/
├── frontend/          # Next.js 前端（Roam）
├── backend/           # Flask + LangGraph 后端（Roam）
├── config/            # API 配置，本地敏感信息不提交
├── data/              # SQLite POI 缓存
└── README.md
```

## 快速启动

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

默认地址：

- 后端：http://127.0.0.1:5000
- 前端：http://localhost:3000

## 配置

`config/api_config.json` 需要包含：

```json
{
  "amap_key": "高德地图 Web 服务 Key",
  "tavily_key": "Tavily Key，可选",
  "model": {
    "qa_agent": {
      "model_name": "OpenAI兼容模型名",
      "api_key": "模型 API Key",
      "base_url": "OpenAI兼容 base_url"
    }
  }
}
```

## API

`POST /api/chat`

```json
{
  "message": "威海，周六一天，2人，预算600，喜欢海边、美食和咖啡，少排队",
  "session_id": "default"
}
```

响应包含：

```json
{
  "reply": "Markdown 路线说明",
  "itinerary": {
    "plan_name": "综合推荐",
    "blocks": [],
    "connections": [],
    "total_duration": 516,
    "total_price": 82,
    "alternatives": []
  },
  "alternatives": [],
  "intent": "plan"
}
```

其他接口：

- `GET /api/health`
- `POST /api/chat/stream`
- `POST /api/reorder`
- `POST /api/itinerary/adjust`
- `POST /api/ugc/xhs/search`
- `POST /api/ugc/read-page`

UGC 搜索示例：

```json
{
  "query": "潮州 美食 咖啡 小红书",
  "limit": 3
}
```

公开页面读取示例：

```json
{
  "url": "https://example.com",
  "max_chars": 1000
}
```

说明：`/api/ugc/read-page` 只读取无需登录和验证码的公开网页文本；遇到登录墙或验证页会停止返回错误。
