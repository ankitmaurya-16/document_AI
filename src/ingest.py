import os
import json
import shutil
from typing import List, Dict
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

DOCS_DIR="data/docs"
INDEX_DIR="data/index"
FAISS_INDEX_PATH = os.path.join(INDEX_DIR,"faiss.index")
METADATA_PATH = os.path.join(INDEX_DIR,"metadata.json")

CHUNK_SIZE=300
CHUNK_OVERLAP=50

EMBEDDING_MODEL="all-MiniLM-L6-v2"

model=SentenceTransformer(EMBEDDING_MODEL)
def embed(texts:List[str])->np.ndarray:
    return model.encode(texts,normalize_embeddings=True).astype("float32")

def load_text_files(directory:str)->Dict[str,str]:
    document={}
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            path=os.path.join(directory,filename)
            with open(path,"r",encoding="utf-8") as f:
                document[filename]=f.read()
    return document

def chunk_text(text:str,chunk_size:int,overlap:int)-> List[str]:
    chunks=[]
    start=0
    while start<len(text):
        end=start+chunk_size
        chunk=text[start:end]
        chunks.append(chunk)
        start=end-overlap
    return chunks

def ingest():
    if os.path.exists(INDEX_DIR):
        shutil.rmtree(INDEX_DIR)
    os.makedirs(INDEX_DIR,exist_ok=True)
    print("Loading Documents...")
    raw_docs=load_text_files(DOCS_DIR)
    all_chunks=[]
    metadata=[]
    print("Chunking documents")
    for source,text in raw_docs.items():
        chunks=chunk_text(text,CHUNK_SIZE,CHUNK_OVERLAP)
        for i, chunk in enumerate(chunks):
            chunk_id=f"{source}_chunk_{i}"
            all_chunks.append(chunk)
            metadata.append({"chunk_id":chunk_id,"source":source,"text":chunk})
    print(f"Total chunks:{len(all_chunks)}")
    print("Embedding chunks...")
    embeddings=embed(all_chunks)
    dim=embeddings.shape[1]
    print("Building Faiss index...")
    index=faiss.IndexFlatIP(dim)
    index.add(embeddings)
    print(f"Vectors indexed: {index.ntotal}")
    print("Saving index metadata...")
    faiss.write_index(index, FAISS_INDEX_PATH)
    with open(METADATA_PATH,"w",encoding="utf-8") as f:
        json.dump(metadata,f,indent=2)
    print("Ingestion complete.")
    
if __name__=="__main__":
    ingest()