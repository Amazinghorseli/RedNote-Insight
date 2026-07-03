# ADR-001: 选择 ChromaDB 而非 Milvus / Pinecone

- **状态**：✅ 已采纳
- **日期**：2025-06
- **决策者**：项目作者

---

## 背景

项目需要一个向量数据库来存储和检索小红书笔记的 Embedding 向量。当前数据量约 166 篇笔记（166 chunks），预期短期内不会超过十万级。

候选方案：

| | ChromaDB | Milvus | Pinecone | PG+pgvector |
|---|---|---|---|---|
| **部署** | `pip install` | Docker/K8s | SaaS | Docker |
| **持久化** | ✅ SQLite | ✅ | ✅ | ✅ |
| **分布式** | ❌ | ✅ | ✅ | ✅ |
| **学习成本** | 极低 | 高 | 中 | 中 |
| **免费** | ✅ | ✅ | ❌ | ✅ |
| **Git 可提交** | ✅ | ❌ | ❌ | ❌ |

## 决策

**选择 ChromaDB，同时预留 PG+pgvector 双模式切换路径。**

```python
# src/core/state.py — 优先 PG，回退 ChromaDB
if settings.database_url:
    try:
        pg_store = await create_pg_vectorstore()
        if pg_store is not None:
            vectorstore = pg_store  # 使用 PG
    except Exception:
        pass
if vectorstore is None:
    vectorstore = load_vectorstore()  # 回退 ChromaDB
```

## 后果

**正面：**
- 10 行代码即可完成 Embedding → 存储 → 检索全流程
- `chroma.sqlite3` 可直接提交 Git，Streamlit Cloud 冷启动时加载已有索引，省去 30-60 秒 embed 时间
- 零运维成本，适合个人项目和早期阶段

**负面：**
- 不支持分布式，数据量到上亿级需迁移到 Milvus 或 Qdrant
- Python-only，非 Python 技术栈选型受限
- 社区较新（2022 年发布），生态不如 Milvus（2019）成熟

**缓解措施：**
- 通过 `PGVectorStore` 适配器预留了 PG+pgvector 升级路径，只需配置 `DATABASE_URL` 环境变量即可切换

## 备选方案

1. **Milvus** — 分布式能力强，但本地开发需要 Docker，太重。当前阶段是过度工程。
2. **Pinecone** — 功能最强但付费，且数据绑在第三方平台，不适合展示项目。
3. **纯 FAISS** — 无持久化，每次重启需重建索引，不可接受。
4. **PG+pgvector** — 已实现适配器作为升级路径保留。

## 面试话术

> "当前规模（166 chunks、百万级向量以内），ChromaDB 嵌入式架构最合适——零运维、Git 可提交。同时已实现 PG+pgvector 适配器，配一个环境变量就升级到生产方案。小规模用 ChromaDB 是权衡后的最优解，不是偷懒。"
