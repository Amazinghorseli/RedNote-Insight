"""
ingestion.py - 文档加载 + 向量库构建
合并自原 step01_ingestion + step02_vectorstore
"""
import os
from langchain_community.document_loaders import TextLoader, DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import RAW_DIR, CHROMA_DIR, EMBEDDING_CONFIG


# ===== 文档加载 =====
def load_raw_documents() -> list[Document]:
    """加载 data/raw/ 下的所有 .md 文件，去掉 frontmatter 和评论分析区"""
    loader = DirectoryLoader(
        str(RAW_DIR),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    loader_txt = DirectoryLoader(
        str(RAW_DIR),
        glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    raw_docs = loader.load() + loader_txt.load()

    # 去掉 YAML frontmatter（--- ... ---）
    import re
    for doc in raw_docs:
        text = doc.page_content
        # 去掉 frontmatter
        text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
        # 去掉 HTML 评论分析区
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        doc.page_content = text.strip()

    print(f"[加载] 加载了 {len(raw_docs)} 个原始文档")
    return raw_docs


def chunk_documents(documents: list[Document], chunk_size=512, overlap=64) -> list[Document]:
    """将文档切分为固定大小 chunk
    小红书笔记每篇约 200-500 字，512 能较好保持内容完整
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", ".", " "],
    )
    chunks = splitter.split_documents(documents)
    print(f"[切分] {len(documents)} 篇文档 -> {len(chunks)} 个 chunk")
    return chunks


# ===== Embedding =====
def get_embeddings() -> OpenAIEmbeddings:
    """创建 Embedding 模型实例"""
    return OpenAIEmbeddings(
        model=EMBEDDING_CONFIG["model"],
        api_key=EMBEDDING_CONFIG["api_key"],
        base_url=EMBEDDING_CONFIG["base_url"],
    )


# ===== 向量库 =====
def build_vectorstore(chunks: list[Document]) -> Chroma:
    """创建并持久化向量库"""
    embeddings = get_embeddings()
    os.makedirs(CHROMA_DIR, exist_ok=True)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    count = vectorstore._collection.count()
    print(f"[向量库] 已创建，共 {count} 个向量 -> {CHROMA_DIR}")
    return vectorstore


def load_vectorstore() -> Chroma:
    """加载已存在的向量库"""
    embeddings = get_embeddings()
    return Chroma(
        persist_directory=str(CHROMA_DIR),
        embedding_function=embeddings,
    )


def incremental_ingest(raw_dir: str, vectorstore: Chroma) -> list:
    """
    增量入库：只加载上次 ingest 之后新增的文件，添加到已有向量库。
    返回新增的 chunks（用于更新 BM25 / HybridRetriever）。

    用法：
        new_chunks = incremental_ingest(str(RAW_DIR), vectorstore)
    """
    import re
    from langchain_community.document_loaders import TextLoader, DirectoryLoader

    # 1. 加载所有 .md 文件（包括已有的，Chromadb 内置去重）
    loader = DirectoryLoader(
        str(raw_dir), glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    loader_txt = DirectoryLoader(
        str(raw_dir), glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    all_docs = loader.load() + loader_txt.load()

    # 2. 清理 frontmatter 和 HTML 注释
    for doc in all_docs:
        text = doc.page_content
        text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        doc.page_content = text.strip()

    # 3. 只 chunk 全部文档，然后添加到向量库
    # Chromadb 的 add_documents 会根据 doc id 自动去重
    new_chunks = chunk_documents(all_docs, chunk_size=512, overlap=64)

    if new_chunks:
        vectorstore.add_documents(new_chunks)
        count = vectorstore._collection.count()
        print(f"[增量入库] 添加 {len(new_chunks)} 个 chunk，向量库总量: {count}")

    return new_chunks


def rebuild_all_chunks(raw_dir: str) -> list:
    """
    重新加载全部文档并 chunk，用于重建 BM25 索引。
    返回完整的 chunks 列表。
    """
    import re
    from langchain_community.document_loaders import TextLoader, DirectoryLoader

    loader = DirectoryLoader(
        str(raw_dir), glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    loader_txt = DirectoryLoader(
        str(raw_dir), glob="**/*.txt",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=False,
    )
    all_docs = loader.load() + loader_txt.load()

    for doc in all_docs:
        text = doc.page_content
        text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        doc.page_content = text.strip()

    return chunk_documents(all_docs, chunk_size=512, overlap=64)
