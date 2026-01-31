import os
import json
import shutil
from typing import List, Dict
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None
try:
    from docx import Document
except ImportError:
    Document = None
try:
    import pandas as pd
except ImportError:
    pd = None
try:
    from pptx import Presentation
except ImportError:
    Presentation = None
from config import (
    DOCS_DIR,
    INDEX_DIR,
    FAISS_INDEX_PATH,
    METADATA_PATH,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_MODEL_NAME,
)

model = SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed(texts: List[str]) -> np.ndarray:
    return model.encode(
        texts,
        normalize_embeddings=True
    ).astype("float32")


# Document Loading


def extract_text_from_file(file_path: str) -> str:
    """Extract text from various file formats."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    
    elif ext == ".pdf":
        if PdfReader is None:
            raise ImportError("PyPDF2 is required for PDF files. Install with: pip install PyPDF2")
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    
    elif ext in [".doc", ".docx"]:
        if Document is None:
            raise ImportError("python-docx is required for Word files. Install with: pip install python-docx")
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    
    elif ext == ".csv":
        if pd is None:
            raise ImportError("pandas is required for CSV files. Install with: pip install pandas")
        df = pd.read_csv(file_path)
        return df.to_string()
    
    elif ext in [".xlsx", ".xls"]:
        if pd is None:
            raise ImportError("pandas is required for Excel files. Install with: pip install pandas openpyxl")
        df = pd.read_excel(file_path)
        return df.to_string()
    
    elif ext in [".ppt", ".pptx"]:
        if Presentation is None:
            raise ImportError("python-pptx is required for PowerPoint files. Install with: pip install python-pptx")
        prs = Presentation(file_path)
        text = ""
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
        return text
    
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def load_text_files_from_dir(directory: str) -> Dict[str, str]:
    documents = {}
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            path = os.path.join(directory, filename)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                documents[filename] = f.read()
    return documents


def load_text_files_from_paths(file_paths: List[str]) -> Dict[str, str]:
    documents = {}
    for path in file_paths:
        filename = os.path.basename(path)
        try:
            text = extract_text_from_file(path)
            documents[filename] = text
        except Exception as e:
            print(f"Error loading {filename}: {e}")
    return documents


# Chunking


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    chunks = []
    text_length = len(text)
    start = 0

    while start < text_length:
        approx_end = min(start + chunk_size, text_length)
        end = approx_end

        while end < text_length and not text[end].isspace():
            end += 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        next_start = end - overlap

        while next_start > start and next_start > 0 and not text[next_start - 1].isspace():
            next_start -= 1

        if next_start <= start:
            next_start = end

        start = next_start

    return chunks


# Core Ingestion Logic (SHARED)


def ingest_documents(documents: Dict[str, str]):
    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)
    os.makedirs(INDEX_DIR, exist_ok=True)

    all_chunks = []
    metadata = []

    for source, text in documents.items():
        chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            metadata.append({
                "chunk_id": f"{source}_chunk_{i}",
                "source": source,
                "text": chunk
            })

    if not all_chunks:
        raise ValueError("No valid text chunks found for ingestion")

    embeddings = embed(all_chunks)
    dim = embeddings.shape[1]

    # FAISS HNSW Index
    M = 32
    ef_construction = 200

    index = faiss.IndexHNSWFlat(dim, M)
    index.hnsw.efConstruction = ef_construction
    index.metric_type = faiss.METRIC_INNER_PRODUCT

    index.train(embeddings)
    index.add(embeddings)

    faiss.write_index(index, FAISS_INDEX_PATH)

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


# CLI Entry
def ingest():
    print("Loading documents from DOCS_DIR...")
    docs = load_text_files_from_dir(DOCS_DIR)
    ingest_documents(docs)
    print("Ingestion complete.")


# Backend Entry 


def ingest_files(file_paths: List[str]):
    print("Loading uploaded files...")
    documents = load_text_files_from_paths(file_paths)

    if not documents:
        raise ValueError("No valid files provided for ingestion")

    ingest_documents(documents)
    print("Ingestion from uploaded files complete.")


if __name__ == "__main__":
    ingest()
