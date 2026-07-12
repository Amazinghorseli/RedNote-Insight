# 🎯 小红书爆款雷达 — AI 选品 + 选题引擎

<p align="center">
  <b>翻评论 · 找痛点 · 定方向 — 一个品类名，两套完整方案</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react" alt="React">
  <img src="https://img.shields.io/badge/Vite-5-646CFF?logo=vite" alt="Vite">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-teal" alt="FastAPI">
  <img src="https://img.shields.io/badge/ChromaDB-0.5+-yellow" alt="ChromaDB">
  <img src="https://img.shields.io/badge/SSE-流式双报告-orange" alt="SSE">
  <img src="https://img.shields.io/badge/BGE_M3-向量模型-orange" alt="BGE-M3">
  <img src="https://img.shields.io/badge/DeepSeek_V3-大模型-purple" alt="DeepSeek">
  <img src="https://img.shields.io/badge/Python-3.11-blue" alt="Python">
  <img src="https://img.shields.io/badge/灵感库-189条精选-green" alt="灵感库">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

---

## 📖 目录

- [🎯 它能做什么](#-它能做什么)
- [🏗️ 系统架构](#️-系统架构)
- [✨ 核心特性](#-核心特性)
- [⚡ 快速开始](#-快速开始)
- [🔧 开发指南](#-开发指南)
- [🐳 Docker 部署](#-docker-部署)
- [🔌 API 文档](#-api-文档)
- [📁 项目结构](#-项目结构)
- [🗺️ 路线图](#️-路线图)

---

## 🎯 它能做什么

输入一个品类名，**同时生成两套完整方案**：

| 报告 | 受众 | 包含 |
|------|------|------|
| 📊 **选品报告** | 电商卖家 | 用户痛点、利润评估、竞争格局、三档定价、避坑提醒 |
| 🎬 **选题方案** | 内容博主 | 3 个爆款选题 + 完整脚本大纲 + 封面方案 + 发布策略 |

### 前端双按钮

| 按钮 | 默认展示 | 适用场景 |
|------|----------|----------|
| 🔍 选品分析 | 选品报告 | 我要卖什么、怎么定价 |
| 🎬 博主方案 | 选题方案 | 我要拍什么、脚本怎么写 |

两份报告都生成完后自动弹出**一键复制导出条**——Markdown 格式，支持一键复制全部 / 下载 .md / 打印 PDF。

### 💡 灵感库

不知道搜什么？左侧栏「灵感库」提供 **9 个品类 × 21 条 = 189 条精选方向**。每条都标注了适用标签（🛒选品 / 🎬选题 / 🛒+🎬 双用），配一句话方向提示。点击直接搜，零等待。

### 报告示例

搜「辣条」输出（即使 LLM 欠费，模板兜底照样出）：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 电商选品洞察报告 — 辣条
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【利润空间评估】
平均售价：¥10-30 | 预估利润率：65% | 定价倍率：3x

【用户痛点 TOP 5】
1. 性价比问题（22%）— "比实体店贵一倍"
2. 质量不稳定（18%）— "批次差异大，每次味道不一样"
3. 包装简陋（15%）— "送礼拿不出手"
4. 口味单一（12%）— "希望出创新风味"
5. 售后缺失（10%）— "漏油不退货"

【三档定价选品】
💰 低价位 ¥9.9 → 麻辣素肉小包装，利润率 65%
💰 中价位 ¥28  → 地域风味礼盒，利润率 71%
💰 高价位 ¥68  → 国潮联名礼盒+花茶，利润率 74%

【选品综合评分】71/100
一句话：用"地域风味+社交属性"破局巨头垄断。
```

---

## 🏗️ 系统架构

```
┌──────────────────────────────────────────────────┐
│  前端：React 18 + Vite 5 + SSE + 双 Tab + 灵感库   │
│  双按钮（选品分析 / 博主方案）+ 一键导出             │
├──────────────────────────────────────────────────┤
│  API：FastAPI 全异步 + 11 路由 + 依赖注入           │
├──────────────────────────────────────────────────┤
│  Agent 管道：                                      │
│    混合检索 → 评论分析 → 需求聚合                   │
│    ├→ InsightGenerator  → 📊 选品报告              │
│    └→ CreatorGenerator   → 🎬 选题方案              │
├──────────────────────────────────────────────────┤
│  数据：ChromaDB/PG + BM25 + 灵感库(189条)          │
└──────────────────────────────────────────────────┘
```

**数据流：** 用户输入 → 混合检索（向量+BM25+RRF）→ CrossEncoder 重排序 → 评论分析 + 需求聚合 → 两个 Agent 并发生成 → SSE 流式双报告

---

## ✨ 核心特性

### 🔀 混合检索
- **BGE-M3 向量检索**：捕捉中文语义相似性
- **BM25 + jieba**：精确匹配品牌名、型号
- **RRF 融合**：两种排序加权合并
- **CrossEncoder 重排序**：比 LLM-as-Judge 快 10 倍

### 📊 双 Agent 管道
同一份聚合数据，两个 Agent 并行输出：

| Agent | 职责 |
|-------|------|
| **InsightGenerator** | 选品报告：利润空间、用户痛点、三档定价、避坑提醒 |
| **CreatorGenerator** | 选题方案：3 个爆款选题 + 脚本大纲 + 封面 + 发布策略 |

两个 Agent **共用一套检索→分析→聚合管道**，换个 prompt 就让数据产生双倍价值。

### 🌊 SSE 流式双报告
`/api/insight/stream` 一次请求同时推送两份报告：

```
SSE 事件流：
  stage → token:selection（选品报告逐字推送）
        → token:creator   （选题方案逐字推送）
        → done            （导出条出现）
```

### ⚛️ React + Vite 前端（v3.0 新增）

| | v2.0 | v3.0 |
|------|------|------|
| 框架 | 原生 JS (1289 行单文件) | React 18 + Vite 5 |
| 状态管理 | 全局变量 + DOM 查询 | Context + useReducer |
| SSE 流式 | 回调嵌套 | useSSE Hook（请求去重 + AbortController） |
| 搜索锁 | 手动变量 | overlay 状态自动解锁 |
| 组件化 | 无 | 9 个独立组件，职责清晰 |
| 开发体验 | 无热更新 | Vite HMR 热更新 |
| 后端 | 零改动 | 零改动（仅新增 SPA fallback） |

### 💡 灵感库（189 条精选）
- 9 个品类 × 21 条 = 189 条人工精选方向
- 每条标注 🛒选品 / 🎬选题 / 🛒+🎬 双用
- 一句话方向提示，搜了就能出报告
- 纯静态 Python dict，零延迟、零爬虫依赖

### 🛡️ 生产级基础设施
- **Docker + docker-compose**：API + PostgreSQL + Redis 一键部署
- **GitHub Actions CI**：lint → test → build
- **依赖注入**（FastAPI Depends）：全局状态管理 + 测试友好
- **RequestID 中间件**：每个请求 UUID 追踪
- **全局异常处理**：统一 JSON 错误格式
- **限流保护**（slowapi）：可配置 QPS
- **Prompt YAML 管理**：版本控制 + 热重载

---

## 🧠 设计决策

### 为什么做双 Agent（选品 + 选题）？

传统 RAG 是"一个问题→一个答案"。但对同一个评论区数据，电商卖家和内容博主关心的是完全不同的事。**换个 prompt 就让同一份数据产生双倍价值**——这不是技术炫技，是业务驱动的架构选择。

### 为什么混合检索？

| 方案 | 擅长 | 不擅长 |
|------|------|--------|
| 纯向量检索 | 语义相似（"求推荐便宜好用的收纳"） | 品牌名精确匹配 |
| 纯 BM25 | 关键词精确（"磁吸感应灯"） | 语义泛化 |
| RRF 融合 | 取两者长处 | — |

### 为什么从原生 JS 迁移到 React？

原 `app.js` 1289 行单文件，全局变量满天飞，SSE 回调嵌套、搜索锁靠手动变量管理。React 重构后：状态集中在 Context + useReducer，SSE 封装为可复用 Hook，每个 UI 块独立组件。**后端一行未改**——FastAPI 只多了一个 SPA fallback 路由。

### 为什么 SSE 而不是 WebSocket？

RAG 只需要服务端→客户端单向推送。SSE 原生支持自动重连、零依赖，完全够用。

### 为什么 Prompt 用 YAML 管理？

版本控制 + Git 可追踪 + 改 prompt 不重启服务。Prompt 也应该有 CI。

### LLM 欠费了怎么办？

每个 Agent 都有 `generate_fallback()` 兜底。规则引擎 + 数据模板照样出可用报告。AI 是锦上添花，工程要保证雪中送炭。

---

## ⚡ 快速开始

### 你需要什么
- **Python 3.11+**
- **Node.js 18+**（仅前端开发需要）
- **SiliconFlow API Key**（[免费注册](https://siliconflow.cn)）
- **[uv](https://docs.astral.sh/uv/)** 包管理器

### 三步跑起来

```bash
# 1. 克隆项目
git clone https://github.com/Amazinghorseli/RedNote-Insight.git
cd RedNote-Insight

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 3. 构建前端 + 启动后端
cd frontend && npm install && npm run build && cd ..
uv sync
uv run uvicorn src.api.main:app --port 8000
```

浏览器打开 **http://localhost:8000**，FastAPI 自动服务 React SPA。

---

## 🔧 开发指南

### 仅后端开发

```bash
uv sync
uv run uvicorn src.api.main:app --reload --port 8000
# 访问 http://localhost:8000/docs 调试 API
```

### 前后端联调（推荐）

开两个终端：

```bash
# 终端 1：启动 FastAPI
uv run uvicorn src.api.main:app --reload --port 8000
```

```bash
# 终端 2：启动 Vite 开发服务器（HMR 热更新）
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
# Vite 自动代理 /api → localhost:8000
```

| 端口 | 服务 | 场景 |
|:----:|------|------|
| 8000 | FastAPI | 后端开发 / 生产 |
| 5173 | Vite Dev | 前端热更新开发 |

### 生产构建

```bash
cd frontend
npm run build          # 输出到 frontend/dist/
cd ..
uv run uvicorn src.api.main:app --port 8000   # FastAPI 自动检测 dist/ 并服务 React SPA
```

---

## 🐳 Docker 部署

```bash
cp .env.example .env
vim .env  # 填入 OPENAI_API_KEY

# 先构建前端
cd frontend && npm install && npm run build && cd ..

docker-compose up -d
curl http://localhost:8000/api/health
```

| 服务 | 端口 |
|------|:----:|
| API | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |

---

## 🔌 API 文档

启动后访问 **http://localhost:8000/docs**（Swagger UI）

| 端点 | 方法 | 说明 |
|------|:----:|------|
| `/api/health` | GET | 健康检查 |
| `/api/insight/stream` | POST | **SSE 流式双报告**（选品+选题） |
| `/api/insight` | POST | 单次洞察报告 |
| `/api/qa/stream` | POST | 流式问答 |
| `/api/qa` | POST | 单次问答 |
| `/api/opportunities` | GET | 品类机会排行 |
| `/api/trending` | GET | 搜索热词 |
| `/api/inspiration` | GET | 灵感库（支持 `?category=美妆`） |
| `/api/crawl` | POST | 触发数据抓取 |
| `/api/trending/refresh` | POST | 刷新热词 |

### 流式双报告示例

```bash
curl -N -X POST http://localhost:8000/api/insight/stream \
  -H "Content-Type: application/json" \
  -d '{"category":"辣条"}'
```

---

## 📁 项目结构

```
RedNote-Insight/
├── frontend/                     # ⚛️ React + Vite 前端（v3.0）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js            # 代理 /api → localhost:8000
│   └── src/
│       ├── main.jsx              # React 入口
│       ├── App.jsx               # 布局：侧边栏 + 双Tab 内容区
│       ├── api/client.js         # fetch/SSE 封装（7 个端点）
│       ├── context/AppContext.jsx # useReducer 全局状态
│       ├── hooks/
│       │   ├── useSSE.js         # ReadableStream SSE 核心
│       │   ├── useSearchHistory.js
│       │   └── useDebounce.js
│       ├── components/
│       │   ├── Sidebar.jsx       # 灵感库/发现机会 标签切换
│       │   ├── SearchBox.jsx     # 输入 + 快搜 + 历史 + 锁
│       │   ├── TrendingTags.jsx  # 热词 + 刷新
│       │   ├── RankingsList.jsx  # 品类排行 + 评分
│       │   ├── HotlistBoard.jsx  # 灵感库 + 品类筛选
│       │   ├── DetailOverlay.jsx # 双Tab 弹窗 + SSE
│       │   ├── MarkdownRenderer.jsx
│       │   ├── ToastContainer.jsx
│       │   └── Skeleton.jsx
│       ├── styles/style.css
│       └── utils/
│           ├── markdown.js
│           └── constants.js
├── src/
│   ├── api/
│   │   ├── main.py              # FastAPI 应用组装 + SPA fallback
│   │   ├── dependencies.py      # 依赖注入
│   │   └── routes/
│   │       ├── health.py
│   │       ├── qa.py / qa_stream.py
│   │       ├── insight.py / insight_stream.py  # ★ 双报告 SSE
│   │       ├── crawl.py
│   │       ├── opportunities.py
│   │       ├── trending.py
│   │       └── inspiration.py
│   ├── core/
│   │   ├── state.py             # AppState 容器
│   │   ├── prompt_loader.py     # Prompt 加载器
│   │   ├── database.py          # PG 向量库适配
│   │   └── query_utils.py       # 查询清洗
│   ├── agents/
│   │   ├── comment_agent.py     # 评论分析
│   │   ├── demand_agent.py      # 需求聚合
│   │   ├── insight_agent.py     # 选品生成
│   │   └── creator_agent.py     # ★ 选题生成
│   ├── data/inspiration.py      # ★ 灵感库（189条）
│   ├── prompts/                 # Prompt YAML
│   ├── retrievers.py            # 混合检索 + RRF + Reranker
│   ├── ingestion.py             # 文档加载 + 向量化
│   ├── crawler.py / real_crawler.py
│   ├── config.py
│   └── logger.py
├── static/                      # 旧版原生 JS 前端（保留，dist 不存在时回退）
│   ├── index.html
│   ├── css/style.css
│   └── js/app.js                # 1289 行原始实现
├── tests/
├── data/                        # 向量库 + 爬虫数据
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

> ★ = v2.0 新增 | ⚛️ = v3.0 新增

---

## 🗺️ 路线图

| 阶段 | 内容 | 状态 |
|------|------|:----:|
| RAG 管道 + FastAPI + 混合检索 | 核心引擎 | ✅ |
| 真实爬虫 + 全异步 + 依赖注入 | 数据基础 | ✅ |
| SSE 流式双报告 + 灵感库 + 双按钮前端 | v2.0 核心 | ✅ |
| React + Vite 前端重构 | v3.0 前端现代化 | ✅ |
| PG+pgvector 生产部署 | 规模升级 | 📋 |
| 图片视频内容分析 + 小程序 | 生态扩展 | 📋 |

---

## 📄 开源协议

MIT © 2026
