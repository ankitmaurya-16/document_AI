# DocAI – Intelligent Document Q&A with RAG

A full-stack AI-powered document assistant that enables semantic search and intelligent Q&A over your documents using Retrieval-Augmented Generation (RAG).

---

## Overview

DocAI allows users to upload documents (PDF, Word, Excel, PowerPoint, CSV, TXT) and ask natural language questions. The system retrieves relevant content using FAISS vector search and generates accurate, source-cited answers using OpenAI's GPT models.

Built for users who need fast, accurate answers from their document collections without manually searching through files.

---

## Features

- **Multi-format Document Support** – Upload and process PDF, DOCX, XLSX, PPTX, CSV, and TXT files
- **Semantic Search** – FAISS-powered vector similarity search for precise retrieval
- **AI-Powered Answers** – Context-aware responses using GPT-4o-mini with source citations
- **Chat History** – Persistent conversation threads stored in MongoDB
- **Authentication** – Email/password and Google OAuth login
- **Credit System** – Built-in usage tracking and credit management
- **Dark Mode UI** – Clean, responsive React frontend with Tailwind CSS

---

## Tech Stack

| Layer             | Technology                                 |
| ----------------- | ------------------------------------------ |
| **Frontend**      | React 19, Vite, Tailwind CSS, React Router |
| **Backend**       | Flask, Python 3.x                          |
| **Vector Search** | FAISS (Facebook AI Similarity Search)      |
| **Embeddings**    | Sentence Transformers (all-MiniLM-L6-v2)   |
| **LLM**           | OpenAI GPT-4o-mini                         |
| **Database**      | MongoDB                                    |
| **Auth**          | JWT, bcrypt, Google OAuth                  |

---

## Project Structure

```
├── backend/
│   ├── app.py                 # Flask API server
│   ├── requirements.txt       # Python dependencies
│   ├── data/
│   │   └── index/             # FAISS index storage (gitignored)
│   └── rag/
│       ├── auth.py            # Authentication logic
│       ├── config.py          # RAG configuration
│       ├── database.py        # MongoDB operations
│       ├── generate.py        # LLM response generation
│       ├── ingest.py          # Document processing & indexing
│       └── retrieve.py        # Vector search & retrieval
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main application component
│   │   ├── components/
│   │   │   ├── ChatBox.jsx    # Chat interface
│   │   │   ├── Message.jsx    # Message rendering
│   │   │   └── Sidebar.jsx    # Navigation sidebar
│   │   ├── context/
│   │   │   └── AppContext.jsx # Global state management
│   │   └── pages/
│   │       ├── Login.jsx      # Authentication page
│   │       ├── Credits.jsx    # Credit management
│   │       └── Community.jsx  # Community features
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

---

## Installation

### Prerequisites

- Python 3.9+
- Node.js 18+
- MongoDB instance (local or Atlas)
- OpenAI API key

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file in the `backend/` directory:

```env
OPENAI_API_KEY=your_openai_api_key
MONGODB_URI=your_mongodb_connection_string
JWT_SECRET=your_jwt_secret_key
GOOGLE_CLIENT_ID=your_google_oauth_client_id  # Optional
```

Start the backend server:

```bash
python app.py
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

The frontend will be available at `http://localhost:5173`

---

## API Endpoints

### Authentication

| Method | Endpoint             | Description               |
| ------ | -------------------- | ------------------------- |
| POST   | `/api/auth/register` | Register new user         |
| POST   | `/api/auth/login`    | Login with email/password |
| POST   | `/api/auth/google`   | Google OAuth login        |
| GET    | `/api/auth/verify`   | Verify JWT token          |

### Chat & Documents

| Method | Endpoint      | Description                      |
| ------ | ------------- | -------------------------------- |
| POST   | `/api/chat`   | Send message and get AI response |
| POST   | `/api/ingest` | Upload and index documents       |
| GET    | `/api/chats`  | Get user's chat history          |
| GET    | `/api/health` | Health check                     |

### Example Request

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{"prompt": "What are the key findings in the report?"}'
```

---

## How It Works

1. **Document Ingestion** – Files are uploaded, text is extracted, and content is chunked (400 chars with 50 char overlap)
2. **Embedding** – Chunks are converted to vectors using Sentence Transformers
3. **Indexing** – Vectors are stored in a FAISS HNSW index for fast similarity search
4. **Retrieval** – User queries are embedded and matched against the index (top 10 results)
5. **Reranking** – Top 3 most relevant chunks are selected
6. **Generation** – GPT-4o-mini generates an answer using retrieved context with source citations

---

## Configuration

Key settings in [backend/rag/config.py](backend/rag/config.py):

| Parameter              | Default          | Description                 |
| ---------------------- | ---------------- | --------------------------- |
| `EMBEDDING_MODEL_NAME` | all-MiniLM-L6-v2 | Sentence transformer model  |
| `CHUNK_SIZE`           | 400              | Characters per chunk        |
| `CHUNK_OVERLAP`        | 50               | Overlap between chunks      |
| `TOP_K`                | 10               | Initial retrieval count     |
| `RERANK_TOP_K`         | 3                | Final context chunks        |
| `LLM_MODEL_NAME`       | gpt-4.1-mini     | OpenAI model for generation |

---

## Design Decisions

- **FAISS over cloud vector DBs** – Chosen for simplicity and zero additional infrastructure cost; suitable for small-to-medium document sets
- **Sentence Transformers** – Local embeddings avoid API costs and provide fast encoding
- **Chunk overlap** – Prevents context loss at chunk boundaries
- **Source citations** – LLM is prompted to cite sources, improving answer traceability
- **Credit system** – Enables usage metering for potential monetization

---

## Future Improvements

- [ ] Add streaming responses for real-time answer generation
- [ ] Implement batch document ingestion
- [ ] Add support for more file formats (Markdown, HTML)
- [ ] Switch to persistent vector DB (Pinecone/Weaviate) for larger scale
- [ ] Add conversation memory for multi-turn context
- [ ] Implement rate limiting and abuse prevention
- [ ] Add unit and integration tests

---

## Supported File Types

| Format     | Extensions              |
| ---------- | ----------------------- |
| Text       | `.txt`                  |
| PDF        | `.pdf`                  |
| Word       | `.doc`, `.docx`         |
| Excel      | `.xlsx`, `.xls`, `.csv` |
| PowerPoint | `.ppt`, `.pptx`         |

Maximum file size: **16MB**

---

## License

MIT License

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
