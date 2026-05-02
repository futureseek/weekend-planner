# 周末去哪儿 · AI行程规划助手

用聊天的方式描述出行需求，AI生成可拖拽组合的行程图块，画布上以卡片连线方式展示行程路线。

## 项目结构

```
weekend-planner/
├── frontend/          # Next.js 前端
├── backend/           # Flask + LangGraph 后端
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

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # 填入API Key
python app.py
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000
