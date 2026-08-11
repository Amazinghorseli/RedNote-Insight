# 🎯 RedNote Insight — AI-Powered Product & Content Intelligence

> *Mine Xiaohongshu comments. Discover opportunities. Generate reports with evidence.*

[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal)](https://fastapi.tiangolo.com)
[![DeepSeek V4](https://img.shields.io/badge/LLM-DeepSeek_V4-purple)](https://deepseek.com)
[![BGE-M3](https://img.shields.io/badge/Embedding-BGE_M3-orange)](https://huggingface.co/BAAI/bge-m3)
[![SSE](https://img.shields.io/badge/Streaming-SSE-orange)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What It Does · 它能做什么

**English** — RedNote Insight analyzes Xiaohongshu (RedNote) product reviews to generate two parallel AI reports from a single search: a **Product Selection Report** for e-commerce sellers and a **Content Strategy Plan** for bloggers. Every insight is backed by cited review evidence — no hallucinated numbers.

**中文** — 输入一个品类，同时生成两份 AI 报告：面向电商卖家的**选品分析**和面向内容博主的**选题方案**。所有结论绑定评论原文证据，杜绝 LLM 编造数据。

| Report · 报告 | Audience · 受众 | Includes · 包含 |
|---------------|-----------------|-----------------|
| 📊 Product Selection · 选品报告 | E-commerce sellers · 电商卖家 | Pain points, demand signals, brand distribution, evidence comments · 用户痛点、需求信号、品牌分布、证据评论 |
| 🎬 Content Strategy · 选题方案 | Content creators · 内容博主 | 3 viral topics + script outlines + cover design + publishing strategy · 3个爆款选题 + 脚本大纲 + 封面方案 + 发布策略 |

### 💡 Inspiration Library · 灵感库

**English** — Don't know what to search? The sidebar "Inspiration Library" offers **189 curated search directions** across 9 categories. Each entry is tagged (🛒 product / 🎬 content / 🛒+🎬 both) with a one-line prompt. Click to search instantly.

**中文** — 不知道搜什么？左侧栏「灵感库」提供 **9 个品类 × 21 条 = 189 条精选方向**。每条标注适用标签（🛒选品 / 🎬选题 / 🛒+🎬双用），配一句话方向提示。点击直接搜，零等待。

---

## Architecture · 系统架构

```
┌──────────────────────────────────────────────────┐
│  Frontend · 前端                                   │
│  React 18 + Vite 5 · SSE streaming · 9 components │
├──────────────────────────────────────────────────┤
│  API · 接口                                        │
│  FastAPI async · 11 routes · dependency injection │
├──────────────────────────────────────────────────┤
│  Agent Pipeline · Agent 管道                       │
│  Hybrid Retrieval → Comment Analysis → Aggregation│
│    ├→ InsightGenerator  → 📊 Product Report        │
│    └→ CreatorGenerator   → 🎬 Content Plan         │
├──────────────────────────────────────────────────┤
│  Data · 数据                                       │
│  PostgreSQL/pgvector · ChromaDB · Redis            │
└──────────────────────────────────────────────────┘
```

**Data Flow · 数据流**: User input → Hybrid RAG (BGE-M3 + BM25 + RRF) → CrossEncoder Rerank → Comment Analysis + Demand Aggregation → Dual Agent parallel generation → SSE streaming

---

## Key Features · 核心特性

### 🔀 Hybrid Retrieval · 混合检索

**English** — BGE-M3 vector search captures semantic similarity. BM25 + jieba ensures exact brand/model matching. RRF (K=60) fuses heterogeneous scores. CrossEncoder reranks the top results — 10× faster than LLM-as-Judge.

**中文** — BGE-M3 向量检索捕捉中文语义相似性，BM25 + jieba 精确匹配品牌名和型号，RRF（K=60）融合异构分数，CrossEncoder 重排序比 LLM-as-Judge 快 10 倍。

### 📊 Dual Agent Pipeline · 双 Agent 管道

**English** — One retrieval, one aggregation, two agents. `InsightGenerator` produces product selection reports with evidence citations; `CreatorGenerator` generates content plans with scripts and cover strategies. Both stream simultaneously via a single SSE connection.

**中文** — 一次检索、一次聚合，双 Agent 并行：`InsightGenerator` 生成带证据引用的选品报告，`CreatorGenerator` 生成选题脚本和封面方案。两路 Token 经单一 SSE 连接同时推送。

### 🛡️ Trusted Generation · 可信生成

**English** — ReportGuard validates numbers against actual review data. Business metrics (profit, weight, shipping cost) that aren't present in the review data are explicitly returned as `null` — the system refuses to hallucinate entry-barrier conclusions.

**中文** — ReportGuard 按金额、比例、评分、重量和销量进行分语义校验。经营数据缺失时，相关字段显式返回 `null`，拒绝编造入场结论。

### ⚛️ React + Vite Frontend · 现代化前端

**English** — Rebuilt from vanilla JS to React 18 + Vite 5. Custom `useSSE` hook with request deduplication and AbortController. 9 independent components with Context + useReducer state management.

**中文** — 从原生 JS 重构为 React 18 + Vite 5。自定义 `useSSE` Hook 实现请求去重和 AbortController。9 个独立组件，Context + useReducer 状态管理。

### 🛡️ Production Infrastructure · 生产基础设施

**English** — Docker + docker-compose for one-command deployment (API + PostgreSQL + Redis). GitHub Actions CI: lint → test → build. 140 automated tests including 21 trust-generation-specific tests.

**中文** — Docker + docker-compose 一键部署（API + PostgreSQL + Redis）。GitHub Actions CI 流水线：lint → test → build。140 项自动化测试，含 21 项可信生成专项测试。

---

## Quick Start · 快速开始

### Prerequisites · 前置条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (auto-installed by run script)
- API key from [SiliconFlow](https://siliconflow.cn) or [DeepSeek](https://platform.deepseek.com)

### One-Command Launch · 一键启动

```bash
# Windows · Windows 系统
run.bat

# macOS / Linux
chmod +x run.sh && ./run.sh
```

### Manual Setup · 手动配置

```bash
git clone https://github.com/Amazinghorseli/RedNote-Insight.git
cd RedNote-Insight
cp .env.example .env   # Edit .env with your API key · 编辑 .env 填入 API Key
uv sync                # Install dependencies · 安装依赖
uv run python generate_data.py   # Generate demo data · 生成演示数据
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Then open · 然后打开 **http://localhost:8000** and **http://localhost:8000/docs** (Swagger).

### Docker · Docker 部署

```bash
docker-compose up -d
```

---

## Tech Stack · 技术栈

| Layer · 层级 | Technology · 技术 | Purpose · 用途 |
|-------------|-------------------|----------------|
| Frontend · 前端 | React 18, Vite 5, SSE | SPA with real-time streaming · 流式双报告 UI |
| Backend · 后端 | FastAPI, Pydantic v2 | Async API with dependency injection · 全异步 API |
| LLM · 大模型 | **DeepSeek V4** | Report generation · 双报告生成 |
| Embedding · 向量 | BGE-M3 | Semantic search for Chinese text · 中文语义检索 |
| Retrieval · 检索 | BM25 + RRF + CrossEncoder | Hybrid retrieval pipeline · 混合检索引擎 |
| Vector DB · 向量库 | ChromaDB / pgvector | Comment storage & search · 评论存储与检索 |
| Task Queue · 任务 | Celery + Redis | Async ingestion & monitoring · 异步数据导入与监测 |
| Database · 数据库 | PostgreSQL | Business metrics & snapshots · 经营指标与快照 |
| Testing · 测试 | pytest, Vitest | 140 unit tests + E2E · 140 项单测 |
| Infra · 基础设施 | Docker, GitHub Actions | CI/CD pipeline · 持续集成 |

---

## API · 接口

| Endpoint | Method | Description · 描述 |
|----------|--------|---------------------|
| `/api/insight/stream` | POST | Generate dual reports via SSE · SSE 流式生成双报告 |
| `/api/insight` | POST | Generate reports (non-streaming) · 非流式生成报告 |
| `/api/qa` | POST | Q&A over report data · 报告数据问答 |
| `/api/trending` | GET | Trending topics & alerts · 趋势话题与告警 |
| `/api/inspiration` | GET | Inspiration library entries · 灵感库条目 |
| `/health` | GET | Health check · 健康检查 |

Full docs · 完整文档: **http://localhost:8000/docs**

---

## Project Structure · 项目结构

```
RedNote-Insight/
├── frontend/              # React 18 + Vite 5 (9 components)
├── src/
│   ├── api/               # FastAPI routes (11 routes)
│   ├── agents/            # InsightGenerator, CreatorGenerator, comment/demand agents
│   ├── prompts/           # YAML-managed prompt templates
│   ├── data/              # Inspiration library (189 curated directions)
│   ├── domain/            # Pydantic models & schemas
│   ├── pipelines/         # Ingestion & monitoring pipelines
│   ├── repositories/      # Data access layer
│   ├── retrievers.py      # Hybrid retrieval + RRF + reranker
│   ├── config.py          # Settings via pydantic-settings
│   └── crawler.py         # Data collection
├── tests/                 # 140 unit tests
├── data/                  # Demo data & ChromaDB
├── Dockerfile
├── docker-compose.yml
├── run.bat / run.sh       # One-click launchers
└── pyproject.toml
```

---

## Roadmap · 路线图

- [x] Hybrid RAG retrieval (BGE-M3 + BM25 + RRF + CrossEncoder)
- [x] Dual Agent SSE streaming
- [x] ReportGuard trusted generation
- [x] React + Vite frontend migration
- [x] Inspiration library (189 curated directions)
- [x] Docker + CI/CD pipeline
- [x] Upgrade to DeepSeek V4
- [ ] Public demo deployment
- [ ] Multi-platform review support (Douyin, Taobao)
- [ ] Real-time trend monitoring dashboard

---

## License · 许可

MIT © 2026

---

<p align="center">
  <sub>Built with ❤️ for makers and sellers · 为创业者和卖家而生</sub>
</p>
