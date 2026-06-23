"""
prompt_loader.py — Prompt YAML 加载器
==========================================
从 src/prompts/ 目录加载 YAML 格式的 Prompt 模板，
支持版本管理、变量替换、缓存。

用法:
    from src.core.prompt_loader import PromptLoader

    loader = PromptLoader()
    prompt = loader.load("gen_answer", version="v1")
    messages = prompt.format_messages(context="...", question="...")
"""

import os
import re
from pathlib import Path
from functools import lru_cache
from typing import Optional

import yaml
from langchain_core.prompts import ChatPromptTemplate

from src.logger import logger


class PromptLoader:
    """从 YAML 文件加载 Prompt 模板"""

    def __init__(self, prompts_dir: Optional[str] = None):
        if prompts_dir is None:
            # 默认路径：src/prompts/
            prompts_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "prompts",
            )
        self.prompts_dir = Path(prompts_dir)
        self._cache: dict[str, ChatPromptTemplate] = {}

    def _get_prompt_path(self, name: str, version: str = "v1") -> Path:
        """获取 Prompt YAML 文件路径"""
        # 支持多种命名格式：gen_answer_v1.yaml, gen_answer.yaml
        candidates = [
            self.prompts_dir / f"{name}_{version}.yaml",
            self.prompts_dir / f"{name}.yaml",
        ]
        for path in candidates:
            if path.exists():
                return path
        raise FileNotFoundError(
            f"Prompt 文件未找到: {name} (version={version})。"
            f"搜索路径: {[str(c) for c in candidates]}"
        )

    def load(self, name: str, version: str = "v1") -> ChatPromptTemplate:
        """加载 Prompt 模板（带缓存）

        Args:
            name: Prompt 名称（不含版本后缀），如 "gen_answer"
            version: 版本后缀，如 "v1"

        Returns:
            ChatPromptTemplate 实例，可直接 .format_messages(**kwargs)
        """
        cache_key = f"{name}_{version}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self._get_prompt_path(name, version)

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        system = data.get("system", "")
        human = data.get("human", "")

        template = ChatPromptTemplate.from_messages([
            ("system", system.strip()),
            ("human", human.strip()),
        ])

        self._cache[cache_key] = template
        logger.info(
            f"prompt_loaded",
            name=name,
            version=version,
            path=str(path),
        )
        return template

    def load_raw(self, name: str, version: str = "v1") -> dict:
        """加载原始 YAML 数据（不包装为 ChatPromptTemplate）"""
        path = self._get_prompt_path(name, version)
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def list_prompts(self) -> list[dict]:
        """列出所有可用的 Prompt"""
        prompts = []
        if not self.prompts_dir.exists():
            return prompts

        for path in sorted(self.prompts_dir.glob("*.yaml")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                prompts.append({
                    "name": data.get("name", path.stem),
                    "version": data.get("version", "unknown"),
                    "description": data.get("description", ""),
                    "file": path.name,
                })
            except Exception:
                continue

        return prompts

    def invalidate_cache(self, name: Optional[str] = None):
        """清除缓存（用于热重载）"""
        if name is None:
            self._cache.clear()
        else:
            keys_to_delete = [k for k in self._cache if k.startswith(name)]
            for k in keys_to_delete:
                del self._cache[k]

    def reload(self, name: str, version: str = "v1") -> ChatPromptTemplate:
        """强制重新加载（绕过缓存）"""
        cache_key = f"{name}_{version}"
        self._cache.pop(cache_key, None)
        return self.load(name, version)


# ── 单例 ──────────────────────────────────────────
_global_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """获取全局 PromptLoader 单例"""
    global _global_loader
    if _global_loader is None:
        _global_loader = PromptLoader()
    return _global_loader
