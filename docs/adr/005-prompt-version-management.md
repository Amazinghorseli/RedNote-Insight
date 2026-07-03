# ADR-005: Prompt 的 YAML 版本化管理

- **状态**：✅ 已采纳
- **日期**：2025-06
- **决策者**：项目作者

---

## 背景

项目有 4 个 Prompt 模板（洞察报告、选题方案、问答、查询重写），每个 Prompt 都会随模型升级和用户反馈迭代。

常见反模式：Prompt 写成 Python 字符串常量塞在代码里。

```python
# ❌ 反模式
prompt = "你是一个电商选品专家，请基于以下数据..."
```

问题：
- 每次改 Prompt 要改代码、重新部署
- 无法对比不同版本的 Prompt 效果
- Git history 里 Prompt 和代码混在一起，不好追踪

## 决策

**Prompt 用 YAML 文件管理，版本号后缀（v1/v2），通过 PromptLoader 统一加载。**

```
src/prompts/
├── gen_answer_v2.yaml        # QA 问答
├── insight_report_v2.yaml    # 选品洞察报告
├── creator_report_v1.yaml    # 自媒体选题方案
└── rewrite_query_v2.yaml     # 查询重写
```

```python
# src/core/prompt_loader.py
class PromptLoader:
    def load(self, name: str, version: str) -> ChatPromptTemplate:
        """加载指定版本的 Prompt，同一版本只解析一次"""
        key = f"{name}_v{version}"
        if key not in self._cache:
            path = self._dir / f"{name}_v{version}.yaml"
            self._cache[key] = self._parse(path)
        return self._cache[key]

    def reload(self) -> None:
        """热重载所有 Prompt，不重启服务"""
        self._cache.clear()
```

## 后果

**正面：**
- Prompt 可以独立迭代，不同版本并存（`insight_report_v1.yaml` 和 `v2` 可以 A/B 测试）
- Git 可追踪：每次 Prompt 修改有独立的 commit message
- 缓存机制：同一版本只解析一次 YAML，避免重复 I/O
- 热重载：`loader.reload()` 不重启服务换 prompt

**负面：**
- YAML 格式对非技术人员不够友好（但项目目前不需要非技术人员改 Prompt）
- 缺乏 Prompt 效果的自动化评估（这是后续改进方向）

**缓解措施：**
- 所有 Agent 都有 `generate_fallback()` 方法，Prompt 加载失败时走规则模板兜底
- 计划加入 Prompt A/B 测试框架（eval/prompt_ab.py）

## 备选方案

1. **代码内字符串常量** — 被否决。无法版本化、无法热重载。
2. **数据库存储** — 被否决。当前阶段过度工程，增加运维复杂度。
3. **LangSmith Prompt Hub** — 引入外部依赖和付费。当前不需要。

## 面试话术

> "Prompt 是 LLM 应用的'半成品代码'——它决定了输出质量，但更容易被忽视。我的方案：YAML 文件管理 + 版本号后缀 + 带缓存的热重载。同一品类我可以秒切 v1/v2 Prompt 对比效果，所有修改都在 Git history 里有据可查。"
