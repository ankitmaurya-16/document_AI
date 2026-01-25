
# Embedding
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Chunking
CHUNK_SIZE = 400        
CHUNK_OVERLAP = 50      

# Retrieval
TOP_K = 10
SIMILARITY_THRESHOLD = -100  # Very permissive threshold to allow all results

# Reranking
RERANK_TOP_K = 3

# LLM Generation
LLM_MODEL_NAME = "gpt-4.1-mini"
LLM_TEMPERATURE = 0.0
LLM_MAX_OUTPUT_TOKENS = 512

# Paths
DOCS_DIR = "docs"
INDEX_DIR = "data/index"
FAISS_INDEX_PATH = "data/index/faiss.index"
METADATA_PATH = "data/index/metadata.json"
