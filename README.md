# 周末去哪儿 · AI行程规划助手

用聊天的方式描述出行需求，AI生成可拖拽组合的行程图块，画布上以卡片连线方式展示行程路线。

## 项目结构

```
weekend-planner/
├── frontend/          # Next.js 前端
├── backend/           # Flask + LangGraph 后端
├── config/            # API 配置（不提交到 Git）
├── docs/              # 文档
├── data/              # 本地数据（POI知识库等）
└── README.md
```

## 技术栈

- **前端**：Next.js 14 + Tailwind CSS + dnd-kit
- **后端**：Python Flask + LangGraph
- **AI**：多LLM兼容（Claude / OpenAI / DeepSeek）
- **存储**：SQLite

## 快速启动

### 1. 配置 API

在项目根目录创建 `config/api_config.json`：

```json
{
  "amap_key": "高德地图 API Key",
  "tavily_key": "Tavily 搜索 API Key",
  "model": {
    "qa_agent": {
      "model_name": "模型名称",
      "api_key": "API Key",
      "base_url": "API 地址"
    }
  }
}
```

| 字段 | 说明 | 获取方式 |
|------|------|----------|
| `amap_key` | 高德地图 Web 服务 Key，用于 POI 搜索和路线规划 | [高德开放平台](https://lbs.amap.com/) |
| `tavily_key` | Tavily 搜索引擎 Key，用于社媒推荐搜索 | [Tavily](https://tavily.com/) |
| `model.qa_agent` | LLM 配置，支持 OpenAI 兼容格式（Claude / DeepSeek / MiMo 等） | 对应平台 |

### 2. 后端

```bash
cd backend
uv sync          # 安装依赖
uv run python app.py
```

后端运行在 http://127.0.0.1:5000

### 3. 前端

```bash
cd frontend
npm install
npm run dev
```

前端运行在 http://localhost:3000

## API 接口

### POST /api/chat

```json
// 请求
{ "message": "周六下午在杭州，预算300", "session_id": "default" }

// 响应
{
  "reply": "帮你规划好了！",
  "itinerary": { "blocks": [...], "connections": [...] },
  "intent": "plan"
}
```
