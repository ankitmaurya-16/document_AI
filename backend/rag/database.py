import os
import threading
from datetime import datetime, timezone
from typing import Optional, List, Dict
from pymongo import ASCENDING, DESCENDING, MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# MongoDB Connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "rag_chat_app")

_client: Optional[MongoClient] = None
_db = None
_init_lock = threading.Lock()


def _build_client() -> MongoClient:
    """Singleton MongoClient with tuned pooling and timeouts."""
    return MongoClient(
        MONGODB_URI,
        maxPoolSize=int(os.getenv("MONGO_MAX_POOL", "50")),
        minPoolSize=int(os.getenv("MONGO_MIN_POOL", "5")),
        serverSelectionTimeoutMS=int(os.getenv("MONGO_SERVER_TIMEOUT_MS", "5000")),
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
        retryWrites=True,
        appname="docai-backend",
    )


def _ensure_indexes(db) -> None:
    db.users.create_index("email", unique=True)
    db.chats.create_index([("userId", ASCENDING), ("updatedAt", DESCENDING)])
    db.chats.create_index("userId")
    db.chats.create_index("createdAt")
    db.documents.create_index([("userId", ASCENDING), ("uploadedAt", DESCENDING)])
    db.feedback.create_index([("chatId", ASCENDING), ("messageTimestamp", ASCENDING)])
    db.feedback.create_index("userId")


def get_database():
    global _client, _db
    if _db is not None:
        return _db
    with _init_lock:
        if _db is None:
            _client = _build_client()
            _db = _client[DB_NAME]
            try:
                _ensure_indexes(_db)
            except Exception:
                # Indexes can fail to create if the server isn't ready; retry
                # lazily on first real call rather than crashing boot.
                pass
    return _db


# Kept for backwards compatibility with existing imports ``client``/``db``.
def _legacy_get():
    return get_database()


client = None  # populated on first get_database() call
db = None


def close_connection():
    global _client, _db
    with _init_lock:
        if _client is not None:
            _client.close()
        _client = None
        _db = None


#User Operations

def create_user(name: str, email: str, hashed_password: str, provider: str = 'email', provider_id: str = None) -> dict:
    db = get_database()
    user = {
        "name": name,
        "email": email,
        "credits": 100,
        "provider": provider,
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    
    # Only add password for email users
    if hashed_password:
        user["password"] = hashed_password
    
    # Add provider ID for OAuth users
    if provider_id:
        user["providerId"] = provider_id
    
    result = db.users.insert_one(user)
    user["_id"] = str(result.inserted_id)
    if "password" in user:
        del user["password"] 
    return user


def update_user_provider(user_id: str, provider: str, provider_id: str = None) -> bool:
    db = get_database()
    update_data = {"provider": provider, "updatedAt": datetime.utcnow()}
    if provider_id:
        update_data["providerId"] = provider_id
    result = db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_data}
    )
    return result.modified_count > 0


def get_user_by_email(email: str) -> Optional[dict]:
    db = get_database()
    user = db.users.find_one({"email": email})
    if user:
        user["_id"] = str(user["_id"])
    return user


def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_database()
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
            if "password" in user:
                del user["password"] 
        return user
    except Exception:
        return None


def update_user_credits(user_id: str, credits: int) -> bool:
    db = get_database()
    result = db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"credits": credits, "updatedAt": datetime.utcnow()}}
    )
    return result.modified_count > 0


#Chat Operations

def create_chat(user_id: str, user_name: str, name: str = "New Chat") -> dict:
    db = get_database()
    chat = {
        "userId": user_id,
        "userName": user_name,
        "name": name,
        "messages": [],
        "createdAt": datetime.utcnow(),
        "updatedAt": datetime.utcnow()
    }
    result = db.chats.insert_one(chat)
    chat["_id"] = str(result.inserted_id)
    return chat


def get_chat_by_id(chat_id: str) -> Optional[dict]:
    db = get_database()
    try:
        chat = db.chats.find_one({"_id": ObjectId(chat_id)})
        if chat:
            chat["_id"] = str(chat["_id"])
        return chat
    except Exception:
        return None


def get_user_chats(user_id: str) -> List[dict]:
    db = get_database()
    chats = list(db.chats.find(
        {"userId": user_id}
    ).sort("updatedAt", -1))
    
    for chat in chats:
        chat["_id"] = str(chat["_id"])
    return chats


def update_chat_name(chat_id: str, name: str) -> bool:
    db = get_database()
    result = db.chats.update_one(
        {"_id": ObjectId(chat_id)},
        {"$set": {"name": name, "updatedAt": datetime.utcnow()}}
    )
    return result.modified_count > 0


def add_message_to_chat(chat_id: str, message: dict) -> bool:
    db = get_database()
    message["timestamp"] = datetime.now(timezone.utc).timestamp() * 1000 
    result = db.chats.update_one(
        {"_id": ObjectId(chat_id)},
        {
            "$push": {"messages": message},
            "$set": {"updatedAt": datetime.utcnow()}
        }
    )
    return result.modified_count > 0


def add_messages_to_chat(chat_id: str, messages: List[dict]) -> bool:
    db = get_database()
    for msg in messages:
        if "timestamp" not in msg:
            msg["timestamp"] = datetime.now(timezone.utc).timestamp() * 1000
    
    result = db.chats.update_one(
        {"_id": ObjectId(chat_id)},
        {
            "$push": {"messages": {"$each": messages}},
            "$set": {"updatedAt": datetime.utcnow()}
        }
    )
    return result.modified_count > 0


def delete_chat(chat_id: str, user_id: str) -> bool:
    db = get_database()
    result = db.chats.delete_one({
        "_id": ObjectId(chat_id),
        "userId": user_id
    })
    return result.deleted_count > 0


def delete_all_user_chats(user_id: str) -> int:
    db = get_database()
    result = db.chats.delete_many({"userId": user_id})
    return result.deleted_count


def get_recent_messages(chat_id: str, limit: int = 10) -> List[Dict]:
    """Return the last ``limit`` messages of a chat as OpenAI-format turns."""
    if not chat_id:
        return []
    try:
        chat = db_mod_find_chat(chat_id)
    except Exception:
        return []
    if not chat:
        return []
    msgs = chat.get("messages") or []
    tail = msgs[-limit:]
    out: List[Dict] = []
    for m in tail:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content:
            out.append({"role": role, "content": content})
    return out


def db_mod_find_chat(chat_id: str) -> Optional[dict]:
    db = get_database()
    try:
        return db.chats.find_one({"_id": ObjectId(chat_id)})
    except Exception:
        return None


# --- Documents ---------------------------------------------------------------

def insert_document(user_id: str, filename: str, size: int, raw_path: str) -> dict:
    db = get_database()
    doc = {
        "userId": user_id,
        "filename": filename,
        "size": size,
        "rawPath": raw_path,
        "uploadedAt": datetime.utcnow(),
    }
    result = db.documents.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


def list_documents(user_id: str) -> List[Dict]:
    db = get_database()
    docs = list(db.documents.find({"userId": user_id}).sort("uploadedAt", -1))
    for d in docs:
        d["_id"] = str(d["_id"])
        # Never expose server-side paths.
        d.pop("rawPath", None)
    return docs


def get_document(user_id: str, doc_id: str) -> Optional[dict]:
    db = get_database()
    try:
        doc = db.documents.find_one({"_id": ObjectId(doc_id), "userId": user_id})
    except Exception:
        return None
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


def delete_document(user_id: str, doc_id: str) -> bool:
    db = get_database()
    try:
        result = db.documents.delete_one({"_id": ObjectId(doc_id), "userId": user_id})
    except Exception:
        return False
    return result.deleted_count > 0


# --- Feedback ----------------------------------------------------------------

def insert_feedback(
    *, user_id: str, chat_id: str, message_timestamp: float, rating: int,
    comment: str | None = None,
) -> dict:
    """rating: +1 (thumbs up) or -1 (thumbs down). Upserts on (chat, ts)."""
    db = get_database()
    key = {"chatId": chat_id, "messageTimestamp": message_timestamp}
    update = {
        "$set": {
            **key,
            "userId": user_id,
            "rating": rating,
            "comment": comment,
            "updatedAt": datetime.utcnow(),
        },
        "$setOnInsert": {"createdAt": datetime.utcnow()},
    }
    db.feedback.update_one(key, update, upsert=True)
    stored = db.feedback.find_one(key)
    stored["_id"] = str(stored["_id"])
    return stored
