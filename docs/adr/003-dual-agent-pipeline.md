# ADR-003: 双 Agent 并行管道（选品 + 选题）

- **状态**：✅ 已采纳
- **日期**：2025-06
- **决策者**：项目作者

---

## 背景

项目从评论数据中提取商业价值。传统 RAG 是"一个问题 → 一个答案"的单向流水线。但同一份评论区数据对不同角色有不同价值：

- **电商卖家** 关心：利润空间、定价策略、供应链、竞争格局
- **内容博主** 关心：选题方向、脚本结构、封面方案、发布策略

最初做了两个独立 API 端点，各自跑一次检索→分析→聚合→生成流程。这意味着同一个品类被检索**两次**、分析**两次**——白白浪费 LLM 调用和 CrossEncoder 开销。

## 决策

**共用检索→分析→聚合管道，仅生成阶段用两个不同 prompt 的 Agent 并行输出。**

```
评论区数据（聚合后）
    ├→ InsightGenerator  → 📊 选品报告（利润/痛点/定价）
    └→ CreatorGenerator  → 🎬 选题方案（爆款选题/脚本/封面）
```

关键代码架构：

```python
# src/agents/insight_agent.py — 选品洞察
class InsightGenerator:
    def _get_prompt(self):
        return self.prompt_loader.load("insight_report", "v2")

# src/agents/creator_agent.py — 选题引擎
class CreatorGenerator:
    def _get_prompt(self):
        return self.prompt_loader.load("creator_report", "v1")

# 两者共用同一份 aggregated 数据
```

## 后果

**正面：**
- 检索和分析只跑一次，第二条报告生成成本近乎为零
- 两个 Agent 完全解耦，可以独立迭代 prompt 版本
- 都有 `generate_fallback()` 兜底方法，LLM 欠费时也能出可用报告

**负面：**
- 两个 Agent 串行生成（先选品后选题），总耗时翻倍
- 不适合超过 3 个 Agent 的场景（复杂度指数增长）

**缓解措施：**
- 已在 prompt 版本管理上做了独立化：`creator_report_v1.yaml` vs `insight_report_v2.yaml` 互不影响
- fallback 方法确保即使 LLM 不可用，用户仍能得到基于模板的结构化报告

## 备选方案

1. **单个通用 Agent** — 一个 prompt 同时输出选品+选题。问题：prompt 过长导致 LLM 聚焦能力下降，且两种报告格式差异大，混在一起质量差。
2. **完全独立的两个 pipeline** — 浪费检索和分析开销。同一个品类搜两次、重排序两次。
3. **LangGraph 多 Agent 编排** — v1.0 使用过 LangGraph supervisor 模式。后来在 v2.0 精简时删除，因为对当前 2 个 Agent 的场景属于过度抽象。

## 面试话术

> "这是业务驱动的架构选择，不是技术炫技。评论区数据对卖家和博主是两种完全不同的价值——选品报告看利润和供应链，选题方案看脚本和封面。两个 Agent 共用检索→分析管道，换个 prompt 就让数据产生双倍价值，零额外成本。"
