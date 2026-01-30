import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, Tuple
from functools import wraps
from flask import request, jsonify
from dotenv import load_dotenv

load_dotenv()


JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-jwt-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24 * 7  


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def generate_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_token_from_header() -> Optional[str]:
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]
    return None


def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_header()
        
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        request.user_id = payload.get('user_id')
        request.user_email = payload.get('email')
        
        return f(*args, **kwargs)
    return decorated_function


def register_user(name: str, email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    from rag.database import create_user, get_user_by_email

    existing_user = get_user_by_email(email)
    if existing_user:
        return None, "Email already registered"
    

    if len(password) < 6:
        return None, "Password must be at least 6 characters"
    
    if not name or len(name) < 2:
        return None, "Name must be at least 2 characters"
    

    hashed_password = hash_password(password)
    user = create_user(name, email, hashed_password)
    
    token = generate_token(user['_id'], email)
    
    return {"user": user, "token": token}, None


def login_user(email: str, password: str) -> Tuple[Optional[dict], Optional[str]]:
    from rag.database import get_user_by_email
    
    user = get_user_by_email(email)
    if not user:
        return None, "Invalid email or password"
    
    if not verify_password(password, user['password']):
        return None, "Invalid email or password"

    user_data = {k: v for k, v in user.items() if k != 'password'}

    token = generate_token(user['_id'], email)
    
    return {"user": user_data, "token": token}, None


def verify_user_token(token: str) -> Tuple[Optional[dict], Optional[str]]:
    from rag.database import get_user_by_id
    
    payload = decode_token(token)
    if not payload:
        return None, "Invalid or expired token"
    
    user = get_user_by_id(payload.get('user_id'))
    if not user:
        return None, "User not found"
    
    return user, None
