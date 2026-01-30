import os
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Import RAG functions
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'rag'))

from rag.ingest import ingest_files
from rag.retrieve import retrieve_top_chunks
from rag.generate import generate_answer
from rag.auth import (
    register_user, login_user, verify_user_token, 
    require_auth, get_token_from_header, decode_token
)
from rag.database import (
    get_user_chats, create_chat, get_chat_by_id, 
    add_messages_to_chat, delete_chat, update_chat_name
)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = tempfile.mkdtemp()
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'csv', 'xlsx', 'xls'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    return jsonify({'error': 'File too large. Maximum size is 16MB'}), 413


@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors."""
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'message': 'RAG API is running'}), 200


# AUTH ENDPOINTS
@app.route('/api/auth/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        
        if not all([name, email, password]):
            return jsonify({'error': 'Name, email and password are required'}), 400
        
        result, error = register_user(name, email, password)
        if error:
            return jsonify({'error': error}), 400
        
        return jsonify(result), 201
    except Exception as e:
        print(f"Error in register: {e}")
        return jsonify({'error': 'Registration failed', 'message': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not all([email, password]):
            return jsonify({'error': 'Email and password are required'}), 400
        
        result, error = login_user(email, password)
        if error:
            return jsonify({'error': error}), 401
        
        return jsonify(result), 200
    except Exception as e:
        print(f"Error in login: {e}")
        return jsonify({'error': 'Login failed', 'message': str(e)}), 500


@app.route('/api/auth/verify', methods=['GET'])
def verify():
    try:
        token = get_token_from_header()
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        user, error = verify_user_token(token)
        if error:
            return jsonify({'error': error}), 401
        
        return jsonify({'user': user}), 200
    except Exception as e:
        print(f"Error in verify: {e}")
        return jsonify({'error': 'Verification failed', 'message': str(e)}), 500


# CHAT CRUD ENDPOINTS 

@app.route('/api/chats', methods=['GET'])
@require_auth
def get_chats():
    try:
        chats = get_user_chats(request.user_id)
        return jsonify({'chats': chats}), 200
    except Exception as e:
        print(f"Error in get_chats: {e}")
        return jsonify({'error': 'Failed to fetch chats', 'message': str(e)}), 500


@app.route('/api/chats', methods=['POST'])
@require_auth
def create_new_chat():
    try:
        from rag.database import get_user_by_id
        user = get_user_by_id(request.user_id)
        user_name = user.get('name', 'User') if user else 'User'
        
        data = request.get_json() or {}
        chat_name = data.get('name', 'New Chat')
        
        chat = create_chat(request.user_id, user_name, chat_name)
        return jsonify({'chat': chat}), 201
    except Exception as e:
        print(f"Error in create_new_chat: {e}")
        return jsonify({'error': 'Failed to create chat', 'message': str(e)}), 500


@app.route('/api/chats/<chat_id>', methods=['GET'])
@require_auth
def get_single_chat(chat_id):
    try:
        chat = get_chat_by_id(chat_id)
        if not chat:
            return jsonify({'error': 'Chat not found'}), 404
        if chat.get('userId') != request.user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        return jsonify({'chat': chat}), 200
    except Exception as e:
        print(f"Error in get_single_chat: {e}")
        return jsonify({'error': 'Failed to fetch chat', 'message': str(e)}), 500


@app.route('/api/chats/<chat_id>', methods=['PUT'])
@require_auth
def update_chat(chat_id):
    try:
        chat = get_chat_by_id(chat_id)
        if not chat:
            return jsonify({'error': 'Chat not found'}), 404
        if chat.get('userId') != request.user_id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        data = request.get_json()
        
        # Update name if provided
        if 'name' in data:
            update_chat_name(chat_id, data['name'])
        
        # Add messages if provided
        if 'messages' in data and isinstance(data['messages'], list):
            add_messages_to_chat(chat_id, data['messages'])
        
        # Return updated chat
        updated_chat = get_chat_by_id(chat_id)
        return jsonify({'chat': updated_chat}), 200
    except Exception as e:
        print(f"Error in update_chat: {e}")
        return jsonify({'error': 'Failed to update chat', 'message': str(e)}), 500


@app.route('/api/chats/<chat_id>', methods=['DELETE'])
@require_auth
def delete_single_chat(chat_id):
    try:
        success = delete_chat(chat_id, request.user_id)
        if not success:
            return jsonify({'error': 'Chat not found or unauthorized'}), 404
        return jsonify({'message': 'Chat deleted successfully'}), 200
    except Exception as e:
        print(f"Error in delete_single_chat: {e}")
        return jsonify({'error': 'Failed to delete chat', 'message': str(e)}), 500


#RAG CHAT ENDPOINTS 


@app.route('/api/chat/upload', methods=['POST'])
def chat_upload():
    try:
        user_id = None
        token = get_token_from_header()
        if token:
            payload = decode_token(token)
            if payload:
                user_id = payload.get('user_id')
        
        prompt = request.form.get('prompt')
        chat_id = request.form.get('chatId')
        
        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400

        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400

        file_names = [secure_filename(f.filename) for f in files if f.filename]

        file_paths = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                file_paths.append(filepath)
            else:
                return jsonify({
                    'error': f'Invalid file type: {file.filename}. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
                }), 400

        if not file_paths:
            return jsonify({'error': 'No valid files to process'}), 400

        print(f"Ingesting {len(file_paths)} files...")
        ingest_files(file_paths)
        
        from rag.retrieve import reload_index
        reload_index()
        print("Index reloaded successfully")

        print(f"Retrieving relevant chunks for query: {prompt}")
        retrieved_chunks = retrieve_top_chunks(prompt, top_k=5)
        print(f"DEBUG: Retrieved {len(retrieved_chunks)} chunks")
        if retrieved_chunks:
            for i, chunk in enumerate(retrieved_chunks[:3]):
                print(f"  Chunk {i}: score={chunk.get('score', 'N/A'):.4f}, source={chunk.get('source', 'N/A')}")
        else:
            print("DEBUG: No chunks retrieved!")

        if not retrieved_chunks:
            answer = "I don't have enough information to answer this question."
        else:
            print("Generating answer...")
            answer = generate_answer(prompt, retrieved_chunks)

        # Clean up temporary files
        for filepath in file_paths:
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file {filepath}: {e}")

        if user_id:
            from rag.database import get_user_by_id
            
            if not chat_id:
                user = get_user_by_id(user_id)
                user_name = user.get('name', 'User') if user else 'User'
                # Use first few words of prompt as chat name
                chat_name = prompt[:30] + "..." if len(prompt) > 30 else prompt
                new_chat = create_chat(user_id, user_name, chat_name)
                chat_id = new_chat['_id']
            
            # Add messages to chat
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "files": file_names,
                    "isImage": False,
                    "isPublished": False
                },
                {
                    "role": "assistant", 
                    "content": answer,
                    "isImage": False,
                    "isPublished": False
                }
            ]
            add_messages_to_chat(chat_id, messages)
            print(f"Messages saved to chat {chat_id}")

        return jsonify({
            'response': answer,
            'chatId': chat_id
        }), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error in chat_upload: {e}")
        return jsonify({'error': 'Failed to process request', 'message': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    try:
        # Get uploaded files
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({'error': 'No files selected'}), 400

        # Save files temporarily
        file_paths = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                file_paths.append(filepath)
            else:
                return jsonify({
                    'error': f'Invalid file type: {file.filename}. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
                }), 400

        if not file_paths:
            return jsonify({'error': 'No valid files to process'}), 400

        # Ingest uploaded files
        print(f"Ingesting {len(file_paths)} files...")
        ingest_files(file_paths)

        # Reload index after ingestion
        from rag.retrieve import reload_index
        reload_index()
        print("Index reloaded successfully")

        # Clean up temporary files
        for filepath in file_paths:
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file {filepath}: {e}")

        return jsonify({'message': 'Files ingested and index updated successfully'}), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error in upload_files: {e}")
        return jsonify({'error': 'Failed to process request', 'message': str(e)}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        # Check for authenticated user
        user_id = None
        token = get_token_from_header()
        if token:
            payload = decode_token(token)
            if payload:
                user_id = payload.get('user_id')
        
        data = request.get_json()
        prompt = data.get('prompt')
        chat_id = data.get('chatId')
        
        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400

        # Retrieve relevant chunks from existing index
        print(f"Retrieving relevant chunks for query: {prompt}")
        retrieved_chunks = retrieve_top_chunks(prompt, top_k=5)

        if not retrieved_chunks:
            answer = "I don't have enough information to answer this question. Please upload documents first."
        else:
            # Generate answer
            print("Generating answer...")
            answer = generate_answer(prompt, retrieved_chunks)

        # Save messages to database if user is authenticated
        if user_id:
            from rag.database import get_user_by_id
            
            if not chat_id:
                user = get_user_by_id(user_id)
                user_name = user.get('name', 'User') if user else 'User'
                # Use first few words of prompt as chat name
                chat_name = prompt[:30] + "..." if len(prompt) > 30 else prompt
                new_chat = create_chat(user_id, user_name, chat_name)
                chat_id = new_chat['_id']
            
            # Add messages to chat
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "isImage": False,
                    "isPublished": False
                },
                {
                    "role": "assistant", 
                    "content": answer,
                    "isImage": False,
                    "isPublished": False
                }
            ]
            add_messages_to_chat(chat_id, messages)
            print(f"Messages saved to chat {chat_id}")

        return jsonify({
            'response': answer,
            'chatId': chat_id
        }), 200

    except Exception as e:
        print(f"Error in chat: {e}")
        return jsonify({'error': 'Failed to process request', 'message': str(e)}), 500


if __name__ == '__main__':
    print("Starting RAG Flask API...")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Allowed file types: {ALLOWED_EXTENSIONS}")
    app.run(debug=True, host='0.0.0.0', port=5001)
