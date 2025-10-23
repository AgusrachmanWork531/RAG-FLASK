import os
import faiss
import numpy as np
import multiprocessing
from flask import Flask, request, jsonify
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
from werkzeug.utils import secure_filename
import threading
import requests
import json
from flask_socketio import SocketIO, emit


# --- KONFIGURASI ---
DOCUMENTS_DIR = 'documents/'
UPLOAD_FOLDER = DOCUMENTS_DIR

# MODEL 1: MODEL EMBEDDING (SI PUSTAKAWAN)
# Tugasnya adalah mengubah teks menjadi vektor numerik (embeddings).
# Model ini sangat cepat dan efisien untuk menemukan potongan teks yang paling relevan dengan query pengguna.
# Mendukung Bahasa Indonesia
EMBEDDING_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

# MODEL 2: QWEN VIA OLLAMA (SI AHLI)
# Tugasnya adalah menerima query pengguna dan konteks yang relevan (ditemukan oleh Model 1),
# lalu menghasilkan jawaban yang koheren dalam bahasa manusia.
OLLAMA_MODEL_NAME = 'qwen2.5:7b'  # Ganti dengan qwen2.5:3b jika RAM terbatas
OLLAMA_API_URL = 'http://localhost:11434/api/generate'  # Ollama default endpoint

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# initialize Flask and SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

embedding_model_global = None
index_global = None
chunk_texts_global = []

# TAMBAHKAN LOCK UNTUK THREAD SAFETY
model_lock = threading.Lock()


# NORMALISASI VEKTOR
def normalize_vectors(vectors):
    norm = np.linalg.norm(vectors, axis=1, keepdims=True)
    # GUNAKAN NP.WHERE UNTUK MENGHINDARI PEMBAGIAN DENGAN NOL
    safe_norm = np.where(norm == 0, 1.0, norm)
    return vectors / safe_norm


# AMBIL TEKS DARI FILE
def get_text_from_file(filepath):
    text = ""
    if filepath.endswith('.txt'):
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
    elif filepath.endswith('.pdf'):
        try:
            with fitz.open(filepath) as doc:
                for page in doc:
                    text += page.get_text()
        except Exception as e:
            print(f"ERROR MEMBACA FILE PDF {filepath}: {e}")
    return text


# POTONG TEKS MENJADI BAGIAN-BAGIAN KECIL
def chunk_text(text, source_filename):
    chunks = []
    for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
        chunk_text = text[i:i + CHUNK_SIZE]
        chunks.append({"text": chunk_text, "source": source_filename})
    return chunks


# TAMBAHKAN POTONGAN TEKS KE INDEKS
def add_chunks_to_index(chunks):
    global index_global, chunk_texts_global

    new_chunk_texts = [chunk["text"] for chunk in chunks]
    new_embeddings = embedding_model_global.encode(
        new_chunk_texts, show_progress_bar=True)
    new_embeddings = normalize_vectors(new_embeddings.astype('float32'))

    if index_global is None:
        embedding_dim = new_embeddings.shape[1]
        index_global = faiss.IndexFlatIP(embedding_dim)
        print(f"MEMBUAT INDEKS FAISS BARU DENGAN DIMENSI {embedding_dim}")

    index_global.add(new_embeddings)
    chunk_texts_global.extend(new_chunk_texts)

    print(
        f"MENAMBAHKAN {len(new_chunk_texts)} CHUNKS KE INDEKS : {index_global.ntotal} TOTAL CHUNKS SEKARANG.")


# AMBIL KONTEKS YANG RELEVAN
def retrieve_contexts(query, k=3):
    global index_global, embedding_model_global
    try:
        with model_lock:
            query_embedding = embedding_model_global.encode([query])
            query_embedding = normalize_vectors(
                query_embedding.astype('float32'))

            if index_global is None or index_global.ntotal == 0:
                return ["BELUM ADA DOKUMEN YANG DIINDEKS."]

            D, I = index_global.search(query_embedding, k)

            # PERIKSA INDEKS YANG VALID
            valid_indices = [i for i in I[0]
                             if 0 <= i < len(chunk_texts_global)]
            retrieved_chunks = [chunk_texts_global[i] for i in valid_indices]

            return retrieved_chunks if retrieved_chunks else ["TIDAK DITEMUKAN KONTEKS YANG RELEVAN."]
    except Exception as e:
        print(f"ERROR DALAM RETRIEVE_CONTEXTS: {e}")
        return ["ERROR SAAT MENGAMBIL KONTEKS."]


# BUAT JAWABAN MENGGUNAKAN QWEN VIA OLLAMA
def generate_answer_with_qwen(query, contexts):
    """MENGHASILKAN JAWABAN MENGGUNAKAN QWEN MELALUI OLLAMA API."""
    try:
        # Buat prompt untuk Qwen
        prompt_template = """Kamu adalah asisten AI yang membantu menjawab pertanyaan berdasarkan konteks yang diberikan.

KONTEKS:
{context}

PERTANYAAN: {question}

INSTRUKSI:
1. Jawab pertanyaan berdasarkan informasi dari konteks di atas
2. Jika informasi ada di konteks, berikan jawaban yang jelas dan ringkas
3. Jika informasi tidak ada di konteks, katakan "Maaf, saya tidak menemukan informasi tersebut dalam dokumen"
4. Jangan mengarang informasi yang tidak ada di konteks
5. Jawab dalam bahasa Indonesia

JAWABAN:"""

        context_str = "\n\n---\n\n".join(contexts)
        prompt = prompt_template.format(context=context_str, question=query)

        # Kirim request ke Ollama API
        payload = {
            "model": OLLAMA_MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40
            }
        }

        print(
            f"Mengirim request ke Ollama dengan model {OLLAMA_MODEL_NAME}...")

        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=120  # Timeout 2 menit
        )

        if response.status_code == 200:
            result = response.json()
            answer = result.get('response', '').strip()

            if not answer:
                return "Maaf, saya tidak dapat menghasilkan jawaban."

            return answer
        else:
            error_msg = f"Error dari Ollama API: {response.status_code} - {response.text}"
            print(error_msg)
            return f"Maaf, terjadi error saat menghubungi Ollama: {response.status_code}"

    except requests.exceptions.ConnectionError:
        error_msg = "Tidak dapat terhubung ke Ollama. Pastikan Ollama sudah berjalan (jalankan: ollama serve)"
        print(error_msg)
        return error_msg
    except requests.exceptions.Timeout:
        error_msg = "Request timeout. Model Qwen memerlukan waktu terlalu lama untuk merespons."
        print(error_msg)
        return error_msg
    except Exception as e:
        print(f"ERROR SAAT MENGHASILKAN JAWABAN: {e}")
        return f"Maaf, saya mengalami error: {str(e)}"


def generate_answer_with_qwen_streaming(query, contexts, session_id):
    """MENGHASILKAN JAWABAN MENGGUNAKAN QWEN MELALUI OLLAMA API DENGAN STREAMING."""
    try:
        # Buat prompt untuk Qwen
        prompt_template = """Kamu adalah asisten AI yang membantu menjawab pertanyaan berdasarkan konteks yang diberikan.
        KONTEKS:
        {context}
        PERTANYAAN: {question}
        INSTRUKSI:
        1. Jawab pertanyaan berdasarkan informasi dari konteks di atas
        2. Jika informasi ada di konteks, berikan jawaban yang jelas dan ringkas
        3. Jika informasi tidak ada di konteks, katakan "Maaf, saya tidak menemukan informasi tersebut dalam dokumen"
        4. Jangan mengarang informasi yang tidak ada di konteks
        5. Jawab dalam bahasa Indonesia
        JAWABAN:"""
        context_str = "\n\n---\n\n".join(contexts)
        prompt = prompt_template.format(context=context_str, question=query)
        # Kirim request ke Ollama API
        payload = {
            "model": OLLAMA_MODEL_NAME,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "num_predict": 512,
                "num_ctx": 2048,
                "repeat_penalty": 1.1
            }
        }

        print(
            f"Mengirim request ke Ollama dengan model {OLLAMA_MODEL_NAME}...")

        socketio.emit('stream_start', {
            'session_id': session_id,
            'status': 'generating'
        })

        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            timeout=120,  # Timeout 2 menit
            stream=True
        )
        if response.status_code == 200:
            full_answer = ""
            for line in response.iter_lines():
                if line:
                    try:
                        # Parse JSON response dari Ollama
                        chunk_data = json.loads(line.decode('utf-8'))

                        # Ambil token response
                        token = chunk_data.get('response', '')

                        if token:
                            full_answer += token
                            # Emit token ke client via WebSocket
                            socketio.emit('stream_token', {
                                'session_id': session_id,
                                'token': token
                            })

                        # Cek apakah streaming selesai
                        if chunk_data.get('done', False):
                            socketio.emit('stream_end', {
                                'session_id': session_id,
                                'status': 'completed',
                                'full_answer': full_answer
                            })
                            break
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON: {e}")
                        continue

            return full_answer.strip() if full_answer else "Maaf, tidak ada respons yang dihasilkan."
        else:
            error_msg = f"Error dari Ollama API: {response.status_code} - {response.text}"
            print(error_msg)
            socketio.emit('stream_error', {
                'session_id': session_id,
                'error': f"Error dari Ollama API: {response.status_code}"
            })
            return f"Maaf, terjadi error saat menghubungi Ollama: {response.status_code}"
    except requests.exceptions.ConnectionError:
        error_msg = "Tidak dapat terhubung ke Ollama. Pastikan Ollama sudah berjalan (jalankan: ollama serve)"
        print(error_msg)
        socketio.emit('stream_error', {
            'session_id': session_id,
            'error': error_msg
        })
        return error_msg
    except requests.exceptions.Timeout:
        error_msg = "Request timeout. Model Qwen memerlukan waktu terlalu lama untuk merespons."
        print(error_msg)
        socketio.emit('stream_error', {
            'session_id': session_id,
            'error': error_msg
        })
        return error_msg
    except Exception as e:
        error_msg = f"ERROR SAAT MENGHASILKAN JAWABAN: {e}"
        print(error_msg)
        socketio.emit('stream_error', {
            'session_id': session_id,
            'error': str(e)
        })
        return f"Maaf, saya mengalami error: {str(e)}"


@app.route('/ask', methods=['POST'])
def ask_api():
    data = request.json
    if not data or 'query' not in data:
        return jsonify({"error": "TIDAK ADA QUERY YANG DISEDIAKAN"}), 400

    if index_global is None or index_global.ntotal == 0:
        return jsonify({"error": "BELUM ADA DOKUMEN YANG DIINDEKS."}), 400

    query = data['query']

    MAX_QUERY_LENGTH = 1000
    if len(query) > MAX_QUERY_LENGTH:
        return jsonify({"error": f"QUERY MELEBIHI PANJANG MAKSIMUM {MAX_QUERY_LENGTH} KARAKTER."}), 400

    try:
        print(f"MENERIMA QUERY: {query}")

        # Ambil konteks yang relevan
        contexts = retrieve_contexts(query, k=3)

        if isinstance(contexts, list) and contexts and contexts[0].startswith("ERROR"):
            return jsonify({"error": contexts[0]}), 500

        # Generate jawaban menggunakan Qwen
        answer = generate_answer_with_qwen(query, contexts)

        return jsonify({
            "answer": answer,
            "contexts": contexts,
            "model": OLLAMA_MODEL_NAME
        })
    except Exception as e:
        print(f"ERROR SAAT MEMPROSES QUERY: {e}")
        return jsonify({"error": f"TERJADI ERROR INTERNAL: {str(e)}"}), 500


@socketio.on('ask_stream')
def handle_ask_stream(data):
    """HANDLER UNTUK SOCKETIO EVENT 'ask_stream' - STREAMING RESPONSE."""
    try:
        # Validasi input
        if not data or 'query' not in data:
            emit('stream_error', {
                'error': 'TIDAK ADA QUERY YANG DISEDIAKAN'
            })
            return

        if index_global is None or index_global.ntotal == 0:
            emit('stream_error', {
                'error': 'BELUM ADA DOKUMEN YANG DIINDEKS.'
            })
            return

        query = data['query']
        session_id = data.get('session_id', 'default')

        # Validasi panjang query
        MAX_QUERY_LENGTH = 1000
        if len(query) > MAX_QUERY_LENGTH:
            emit('stream_error', {
                'error': f'QUERY MELEBIHI PANJANG MAKSIMUM {MAX_QUERY_LENGTH} KARAKTER.'
            })
            return

        print(f"MENERIMA QUERY STREAMING: {query} (session: {session_id})")

        # Ambil konteks yang relevan
        contexts = retrieve_contexts(query, k=3)

        if isinstance(contexts, list) and contexts and contexts[0].startswith("ERROR"):
            emit('stream_error', {
                'session_id': session_id,
                'error': contexts[0]
            })
            return

        # Emit konteks yang ditemukan
        emit('stream_contexts', {
            'session_id': session_id,
            'contexts': contexts
        })

        # Generate jawaban dengan streaming
        generate_answer_with_qwen_streaming(query, contexts, session_id)

    except Exception as e:
        print(f"ERROR SAAT MEMPROSES QUERY STREAMING: {e}")
        emit('stream_error', {
            'error': f'TERJADI ERROR INTERNAL: {str(e)}'
        })


# API UNTUK MENGUNGGAH FILE
@app.route('/upload', methods=['POST'])
def upload_api():
    """API ENDPOINT UNTUK MENGUNGGAH FILE .TXT ATAU .PDF."""
    if 'file' not in request.files:
        return jsonify({"error": "TIDAK ADA BAGIAN 'FILE' DALAM REQUEST"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "TIDAK ADA FILE YANG DIPILIH"}), 400

    if not (file.filename.endswith(".txt") or file.filename.endswith(".pdf")):
        return jsonify({"error": "TIPE FILE TIDAK VALID. HANYA .TXT DAN .PDF YANG DIIZINKAN."}), 400

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        print(f"FILE DISIMPAN KE {filepath}")

        try:
            text = get_text_from_file(filepath)
            if not text:
                return jsonify({"error": f"TIDAK DAPAT MEMBACA TEKS DARI {filename}"}), 400

            chunks = chunk_text(text, filename)
            add_chunks_to_index(chunks)

            return jsonify({
                "message": f"FILE '{filename}' DIUNGGAH DAN DIPROSES.",
                "new_chunks_added": len(chunks),
                "total_chunks_in_index": index_global.ntotal
            }), 201

        except Exception as e:
            print(f"ERROR SAAT MEMPROSES UPLOAD: {e}")
            return jsonify({"error": f"GAGAL MEMPROSES FILE: {str(e)}"}), 500


# API UNTUK CEK STATUS OLLAMA
@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint untuk cek status sistem dan koneksi Ollama."""
    try:
        # Cek koneksi ke Ollama
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL_NAME,
                "prompt": "test",
                "stream": False
            },
            timeout=5
        )
        ollama_status = "connected" if response.status_code == 200 else "error"
    except:
        ollama_status = "disconnected"

    return jsonify({
        "status": "running",
        "ollama_status": ollama_status,
        "ollama_model": OLLAMA_MODEL_NAME,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "total_documents": index_global.ntotal if index_global else 0
    })


# MEMUAT SEMUA MODEL DAN DOKUMEN
def load_all_models_and_docs():
    """FUNGSI INI BERJALAN SEKALI KETIKA SERVER DIMULAI."""
    global embedding_model_global

    print("=" * 60)
    print("MEMULAI SISTEM RAG DENGAN QWEN (OLLAMA)")
    print("=" * 60)

    print("\n[1/3] MEMUAT MODEL EMBEDDING...")
    embedding_model_global = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print(f"✅ Model embedding '{EMBEDDING_MODEL_NAME}' berhasil dimuat")

    print("\n[2/3] MEMERIKSA KONEKSI OLLAMA...")
    try:
        response = requests.get('http://localhost:11434/api/tags', timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]

            if any(OLLAMA_MODEL_NAME in name for name in model_names):
                print(f"✅ Model Qwen '{OLLAMA_MODEL_NAME}' tersedia di Ollama")
            else:
                print(
                    f"⚠️  WARNING: Model '{OLLAMA_MODEL_NAME}' tidak ditemukan!")
                print(f"   Jalankan: ollama pull {OLLAMA_MODEL_NAME}")
                print(f"   Model tersedia: {model_names}")
        else:
            print("⚠️  WARNING: Ollama berjalan tapi tidak dapat mengambil daftar model")
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Tidak dapat terhubung ke Ollama!")
        print("   Pastikan Ollama sudah diinstall dan berjalan")
        print("   Jalankan: ollama serve")
        print("   Lalu: ollama pull " + OLLAMA_MODEL_NAME)
    except Exception as e:
        print(f"⚠️  WARNING: Error saat cek Ollama: {e}")

    print("\n[3/3] MEMPROSES DOKUMEN YANG SUDAH ADA...")
    processed_files = 0
    for filename in os.listdir(DOCUMENTS_DIR):
        filepath = os.path.join(DOCUMENTS_DIR, filename)
        if os.path.isfile(filepath) and (filepath.endswith(".txt") or filepath.endswith(".pdf")):
            try:
                print(f"   Memproses: {filename}...")
                text = get_text_from_file(filepath)
                if text:
                    chunks = chunk_text(text, filename)
                    add_chunks_to_index(chunks)
                    processed_files += 1
            except Exception as e:
                print(f"   ❌ Error memproses {filename}: {e}")

    if processed_files == 0 and index_global is None:
        print("   ℹ️  Tidak ada dokumen yang diproses. Indeks kosong.")
    else:
        print(f"   ✅ {processed_files} file berhasil diproses")

    print("\n" + "=" * 60)
    print("✅ LAYANAN RAG SIAP!")
    print("=" * 60)
    print(f"📚 Total chunks: {index_global.ntotal if index_global else 0}")
    print(f"🤖 Model LLM: {OLLAMA_MODEL_NAME}")
    print(f"🔍 Model Embedding: {EMBEDDING_MODEL_NAME}")
    print(f"🌐 Server: http://0.0.0.0:9003")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    # GUNAKAN METODE SPAWN UNTUK STABILITAS YANG LEBIH BAIK
    multiprocessing.set_start_method('spawn', force=True)

    # MEMUAT MODEL DAN DOKUMEN SEBELUM SERVER DIMULAI
    load_all_models_and_docs()

    # JALANKAN FLASK SERVER DENGAN SOCKETIO SUPPORT
    # Gunakan socketio.run() untuk mendukung WebSocket streaming
    socketio.run(app, host='0.0.0.0', port=9003, debug=False, allow_unsafe_werkzeug=True)
