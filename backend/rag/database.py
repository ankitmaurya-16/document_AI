import os
from datetime import datetime, timezone
from typing import Optional, List, Dict
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

# MongoDB Connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "rag_chat_app")

client = None
db = None


def get_database():
    global client, db
    if client is None:
        client = MongoClient(MONGODB_URI)
        db = client[DB_NAME]
        # Create indexes
        db.users.create_index("email", unique=True)
        db.chats.create_index("userId")
        db.chats.create_index("createdAt")
    return db


def close_connection():
    global client
    if client:
        client.close()
        client = None


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
    except:
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
    except:
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
