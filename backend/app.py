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


@app.route('/api/chat/upload', methods=['POST'])
def chat_upload():
    """
    Handle file upload and chat query.
    Expects:
        - prompt: string (user question)
        - files: array of files
    Returns:
        - response: string (generated answer)
    """
    try:
        # Get prompt from form data
        prompt = request.form.get('prompt')
        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400

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

        # Step 1: Ingest uploaded files
        print(f"Ingesting {len(file_paths)} files...")
        ingest_files(file_paths)
        
        # Reload index after ingestion
        from rag.retrieve import reload_index
        reload_index()
        print("Index reloaded successfully")

        # Step 2: Retrieve relevant chunks
        print(f"Retrieving relevant chunks for query: {prompt}")
        retrieved_chunks = retrieve_top_chunks(prompt, top_k=5)
        print(f"DEBUG: Retrieved {len(retrieved_chunks)} chunks")
        if retrieved_chunks:
            for i, chunk in enumerate(retrieved_chunks[:3]):  # Show first 3
                print(f"  Chunk {i}: score={chunk.get('score', 'N/A'):.4f}, source={chunk.get('source', 'N/A')}")
        else:
            print("DEBUG: No chunks retrieved!")

        if not retrieved_chunks:
            return jsonify({
                'response': "I don't have enough information to answer this question."
            }), 200

        # Step 3: Generate answer
        print("Generating answer...")
        answer = generate_answer(prompt, retrieved_chunks)

        # Clean up temporary files
        for filepath in file_paths:
            try:
                os.remove(filepath)
            except Exception as e:
                print(f"Error deleting file {filepath}: {e}")

        return jsonify({'response': answer}), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Error in chat_upload: {e}")
        return jsonify({'error': 'Failed to process request', 'message': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_files():
    """
    Handle file upload without chat query.
    Expects:
        - files: array of files
    Returns:
        - message: string (status message)
    """
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
    """
    Handle chat query without file upload.
    Uses existing index from previous uploads.
    Expects:
        - prompt: string (user question)
    Returns:
        - response: string (generated answer)
    """
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        
        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400

        # Retrieve relevant chunks from existing index
        print(f"Retrieving relevant chunks for query: {prompt}")
        retrieved_chunks = retrieve_top_chunks(prompt, top_k=5)

        if not retrieved_chunks:
            return jsonify({
                'response': "I don't have enough information to answer this question. Please upload documents first."
            }), 200

        # Generate answer
        print("Generating answer...")
        answer = generate_answer(prompt, retrieved_chunks)

        return jsonify({'response': answer}), 200

    except Exception as e:
        print(f"Error in chat: {e}")
        return jsonify({'error': 'Failed to process request', 'message': str(e)}), 500


if __name__ == '__main__':
    print("Starting RAG Flask API...")
    print(f"Upload folder: {UPLOAD_FOLDER}")
    print(f"Allowed file types: {ALLOWED_EXTENSIONS}")
    app.run(debug=True, host='0.0.0.0', port=5001)
