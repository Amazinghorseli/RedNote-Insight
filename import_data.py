"""
import_data.py - 真实数据导入工具
=====================================
将 CSV/Excel 中的笔记数据导入为 .md 格式，
兼容现有 RAG 问答 + 洞察管道。

用法：
  # 查看 CSV 格式说明
  python import_data.py --help

  # 导入 CSV（自动生成评论分析数据）
  python import_data.py --input my_data.csv

  # 导入 + 用 LLM 丰富评论分析（需 API Key）
  python import_data.py --input my_data.csv --enrich

  # 导入后自动重建向量库
  python import_data.py --input my_data.csv --rebuild
  python import_data.py --input my_data.xlsx --sheet Sheet1 --rebuild

输入格式：
  title,content,brand,likes,date,tags,comments,author
  标题,笔记正文,品牌名,点赞数,日期,标签|逗号分隔,评论数,作者名

只有 title 和 content 是必填，其余缺失会自动填充默认值。
"""
import os
import sys
import csv
import json
import random
import argparse
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

# 确保能找到 src 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# 评论分析数据自动生成（基于内容关键词）
# ============================================================

# 关键词 → 常见投诉映射
COMPLAINT_KEYWORDS = {
    "续航": ["续航不够持久", "充电太频繁"],
    "价格": ["价格偏高", "性价比一般"],
    "质量": ["质量一般", "用不久就坏了"],
    "材质": ["材质一般", "手感不好"],
    "大小": ["尺寸偏小", "比想象中小"],
    "颜色": ["颜色和图片有差异", "色差严重"],
    "安装": ["安装不方便", "安装说明不清晰"],
    "充电": ["充电太慢", "续航不够持久"],
    "磁吸": ["磁吸不够牢固", "容易掉"],
    "灯": ["亮度不够", "灯光刺眼"],
    "声音": ["噪音有点大", "运行声音明显"],
    "容量": ["容量太小", "装不了多少东西"],
    "设计": ["设计一般", "不够美观"],
    "包装": ["包装简陋", "包装破损"],
    "售后": ["售后服务差", "退货麻烦"],
}

# 关键词 → 常见需求信号映射
INTENT_KEYWORDS = {
    "学生": ["适合学生党吗", "性价比怎么样"],
    "寝室": ["宿舍能用吗", "查寝会被扣分吗"],
    "租房": ["适合租房党吗", "搬家好带走吗"],
    "礼物": ["送人合适吗", "包装好看吗"],
    "新手": ["新手适合吗", "操作难不难"],
    "卧室": ["适合卧室用吗", "什么色温适合卧室"],
    "厨房": ["防水吗", "厨房能用吗"],
    "礼物": ["送人合适吗", "有礼品包装吗"],
    "质量": ["质量怎么样", "耐不耐用"],
    "价格": ["有优惠吗", "什么时候降价"],
    "尺寸": ["尺寸多大", "能放下吗"],
    "颜色": ["有什么颜色", "哪个颜色好看"],
}

# 通用评论高频词
DEFAULT_HIGH_FREQ = ["求链接", "好用吗", "收藏了", "什么牌子", "多少钱"]

# 通用品牌对比
DEFAULT_COMPARISONS = ["比其他品牌性价比高", "比线下便宜"]


def infer_comment_analysis(title: str, content: str, brand: str) -> Dict:
    """从笔记标题+内容中推断可能的评论分析数据"""
    combined = (title + " " + content).lower()
    complaints = []
    intents = []

    # 匹配关键词
    for keyword, complaint_list in COMPLAINT_KEYWORDS.items():
        if keyword in combined:
            complaints.append(random.choice(complaint_list))

    for keyword, intent_list in INTENT_KEYWORDS.items():
        if keyword in combined:
            intents.append(random.choice(intent_list))

    # 保底：至少一条
    if not complaints:
        complaints.append(random.choice(list(COMPLAINT_KEYWORDS.values()))[0])
    if not intents:
        intents.append(random.choice(list(INTENT_KEYWORDS.values()))[0])

    # 去重
    complaints = list(dict.fromkeys(complaints))
    intents = list(dict.fromkeys(intents))

    return {
        "high_freq_words": DEFAULT_HIGH_FREQ.copy(),
        "complaints": complaints[:5],
        "purchase_intent": intents[:5],
        "comparison_mentions": [f"比{brand}便宜多了"] if brand else DEFAULT_COMPARISONS,
        "related_brands": [brand] if brand else [],
        "ask_link_count": random.randint(30, 200),
    }


def enrich_with_llm(title: str, content: str, brand: str, api_key: str = None) -> Optional[Dict]:
    """用 LLM 从内容中提取评论分析（需要设置 LLM API Key）"""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from dotenv import load_dotenv

        load_dotenv()
        llm = ChatOpenAI(
            model=os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash"),
            temperature=0.1,
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是小红书评论分析专家。根据笔记标题和内容，"
             "推断用户可能在评论区讨论什么。返回 JSON 格式：\n"
             '{"complaints": ["投诉1", "投诉2"],'
             ' "purchase_intent": ["需求1", "需求2"],'
             ' "comparison_mentions": ["对比提及1"]}\n'
             "不要解释，只返回 JSON。"),
            ("human", "标题：{title}\n内容：{content}"),
        ])

        msg = prompt.format_messages(title=title, content=content[:500])
        result = llm.invoke(msg).content.strip()
        # 提取 JSON
        json_match = re.search(r"\{.*\}", result, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            data["high_freq_words"] = DEFAULT_HIGH_FREQ.copy()
            data["related_brands"] = [brand] if brand else []
            data["ask_link_count"] = random.randint(30, 200)
            return data
    except Exception as e:
        print(f"  LLM 分析失败: {e}")
    return None


# ============================================================
# 数据导入
# ============================================================

def parse_value(value: str) -> Any:
    """智能解析 CSV 中的值"""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    # 数字
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    # 布尔
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    return value


def read_csv(filepath: str) -> List[Dict]:
    """读取 CSV 文件"""
    records = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = {k: parse_value(v) for k, v in row.items()}
            records.append(record)
    return records


def read_excel(filepath: str, sheet: str = None) -> List[Dict]:
    """读取 Excel 文件"""
    try:
        import pandas as pd
    except ImportError:
        print("[错误] 读取 Excel 需要安装 pandas：pip install pandas openpyxl")
        sys.exit(1)

    if sheet:
        df = pd.read_excel(filepath, sheet_name=sheet)
    else:
        df = pd.read_excel(filepath)
    return df.to_dict(orient="records")


def generate_md(
    record: Dict,
    output_dir: str,
    index: int,
    use_llm: bool = False,
) -> str:
    """将一条记录转换为 .md 文件内容"""
    # 字段名大小写兼容
    title = str(record.get("title") or record.get("Title") or f"笔记{index}")
    content = str(record.get("content") or record.get("Content") or record.get("正文", ""))
    brand = str(record.get("brand") or record.get("Brand") or record.get("品牌", ""))
    likes = int(record.get("likes") or record.get("Likes") or record.get("点赞", 0) or random.randint(100, 500))
    date_val = record.get("date") or record.get("Date") or record.get("日期", "")
    tags_raw = record.get("tags") or record.get("Tags") or record.get("标签", "")
    author = record.get("author") or record.get("Author") or record.get("作者", f"小红书用户{random.randint(1000,9999)}")
    comments_count = record.get("comments") or record.get("Comments") or record.get("评论数", 0) or int(likes * random.uniform(0.15, 0.35))

    # 标签解析（CSV 中可能是逗号分隔或竖线分隔）
    if isinstance(tags_raw, str):
        sep = "|" if "|" in tags_raw else ","
        tags = [t.strip() for t in tags_raw.split(sep) if t.strip()]
    elif isinstance(tags_raw, list):
        tags = tags_raw
    else:
        tags = [brand, "小红书好物"]

    # 日期格式统一
    if not date_val:
        date_val = f"2025-{random.randint(1,5):02d}-{random.randint(1,28):02d}"
    else:
        try:
            date_val = str(pd.Timestamp(date_val).date())
        except Exception:
            pass

    # 评论分析数据
    if use_llm:
        ca_data = enrich_with_llm(title, content, brand)
    else:
        ca_data = infer_comment_analysis(title, content, brand)

    if ca_data is None:
        ca_data = infer_comment_analysis(title, content, brand)

    # 文件名：品类_序号.md
    category_slug = brand[:2] if brand else "import"
    filename = f"{category_slug}_{index:03d}.md"
    filepath = os.path.join(output_dir, filename)

    # 处理 content 中可能包含的 ---（会被 YAML 解析器误读）
    content_clean = content.replace("---", "—")

    # 组装文件
    parts = [
        "---\n",
        f'title: "{title}"\n',
        f'author: "{author}"\n',
        f"likes: {likes}\n",
        f"comments: {comments_count}\n",
        f"date: {date_val}\n",
        f'brand: "{brand}"\n',
        f"tags: {tags}\n",
        "---\n\n",
        content_clean,
        "\n---\n",
        "<!--\n",
        "comment_analysis:\n",
        f"  high_freq_words: {ca_data['high_freq_words']}\n",
        f"  complaints: {ca_data['complaints']}\n",
        f"  purchase_intent: {ca_data['purchase_intent']}\n",
        f"  comparison_mentions: {ca_data['comparison_mentions']}\n",
        f"  related_brands: {ca_data['related_brands']}\n",
        f"  ask_link_count: {ca_data['ask_link_count']}\n",
        "-->\n",
    ]

    return "".join(parts), filename


def rebuild_vectorstore():
    """重建向量库"""
    print("\n[重建] 重建向量库...")
    try:
        from src.ingestion import load_raw_documents, chunk_documents, build_vectorstore
        docs = load_raw_documents()
        chunks = chunk_documents(docs)
        build_vectorstore(chunks)
        print(f"[重建] 完成：{len(chunks)} 个文档已向量化")
    except Exception as e:
        print(f"[重建失败] {e}")
        print("你可以稍后手动重建：python -c 'from src.ingestion import *; rebuild()'")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="将 CSV/Excel 数据导入为小红书笔记 .md 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例 CSV 格式（utf-8 编码）：
  title,content,brand,likes,date,tags,comments,author
  瑜伽裤测评,这条瑜伽裤真的绝了...,lululemon,534,2025-03-01,运动|瑜伽,128,小雅
  平价健身服推荐,学生党必看的健身服...,Alo,312,2025-02-15,健身|平价,56,阿宁

字段说明：
  title*   笔记标题（必填）
  content* 笔记正文（必填）
  brand    品牌名
  likes    点赞数
  date     发布日期
  tags     标签，竖线 | 分隔
  comments 评论数
  author   作者名

导入后，在洞察模式输入品类名即可生成选品报告。
        """,
    )
    parser.add_argument("--input", "-i", default=None, help="CSV 或 Excel 文件路径")
    parser.add_argument("--sheet", "-s", help="Excel 工作表名（默认第一页）")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="输出目录（默认 data/raw）")
    parser.add_argument("--enrich", action="store_true",
                        help="用 LLM 从内容中提取评论分析（需配置 API Key）")
    parser.add_argument("--rebuild", action="store_true",
                        help="导入后重建向量库")
    parser.add_argument("--sample", action="store_true",
                        help="生成示例 CSV 文件到当前目录")

    args = parser.parse_args()

    # ---- 既不是示例也不是导入 ----
    if not args.sample and not args.input:
        parser.print_help()
        print("\n使用 --sample 生成示例 CSV，或使用 --input 导入数据。")
        return

    # ---- 生成示例 ----
    if args.sample:
        sample_path = os.path.join(os.getcwd(), "sample_data.csv")
        with open(sample_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["title", "content", "brand", "likes", "date", "tags", "comments", "author"])
            writer.writerow(["瑜伽裤测评", "这条瑜伽裤真的太绝了！弹性超好，包裹感强，深蹲完全不会透。", "lululemon", "534", "2025-03-01", "运动|瑜伽|健身", "128", "小雅"])
            writer.writerow(["平价健身服推荐", "学生党必看！百元以内的健身服分享，透气舒适，适合健身房。", "Alo", "312", "2025-02-15", "健身|平价|学生党", "56", "阿宁"])
            writer.writerow(["跑步鞋开箱", "新入的跑鞋太香了，减震效果很好，马拉松训练穿它。", "Nike", "678", "2025-01-20", "跑步|运动|开箱", "203", "跑者小王"])
        print(f"[示例] 已生成示例文件：{sample_path}")
        print("[示例] 参考此格式准备你的数据，然后运行：")
        print(f"  python import_data.py --input {sample_path}")
        return

    # ---- 导入 ----
    filepath = args.input
    if not os.path.exists(filepath):
        print(f"[错误] 文件不存在：{filepath}")
        sys.exit(1)

    # 确定输出目录
    project_root = os.path.dirname(os.path.abspath(__file__))
    output_dir = args.output_dir or os.path.join(project_root, "data", "raw")
    os.makedirs(output_dir, exist_ok=True)

    # 读取
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xls"):
        print(f"[读取] Excel: {filepath}")
        records = read_excel(filepath, args.sheet)
    elif ext == ".csv":
        print(f"[读取] CSV: {filepath}")
        records = read_csv(filepath)
    elif ext == ".json":
        with open(filepath, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        print(f"[错误] 不支持的文件格式：{ext}，请使用 CSV 或 Excel")
        sys.exit(1)

    # 生成
    print(f"[导入] 共 {len(records)} 条记录")
    if args.enrich:
        print("[导入] LLM 评论分析已开启（每个笔记需要一次 API 调用）")

    count = 0
    for i, record in enumerate(records):
        try:
            md_content, filename = generate_md(record, output_dir, i + 1, use_llm=args.enrich)
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
            print(f"  + {filename}")
            count += 1
        except Exception as e:
            print(f"  ✗ 第 {i+1} 行导入失败: {e}")

    print(f"\n=> 成功导入 {count}/{len(records)} 篇笔记 -> {output_dir}")

    if args.rebuild:
        rebuild_vectorstore()
    else:
        print("\n提示: 使用 --rebuild 参数重建向量库，或删除 data/chroma_db 目录后重启应用。")
        print("启动应用：streamlit run app.py")


if __name__ == "__main__":
    main()
