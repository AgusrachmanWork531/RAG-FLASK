# RAG-FLASK: Tanya Jawab Dokumen dengan AI

Aplikasi web untuk "berbicara" dengan dokumen Anda. Upload PDF/TXT, tanya dalam bahasa Indonesia, dapatkan jawaban kontekstual menggunakan RAG (Retrieval-Augmented Generation).

## Fitur

- **Upload Dokumen**: Format `.pdf` dan `.txt`
- **Tanya Jawab Streaming**: Jawaban real-time token-by-token via WebSocket
- **Model Lokal**: LLM via [Ollama](https://ollama.ai/) - data tetap privat
- **Embedding Multilingual**: Pencarian semantik bahasa Indonesia

## Quick Start

```bash
# 1. Start server
./run_script.sh

# 2. Open test client
open test_streaming.html

# 3. Upload dokumen → Tanya!
```

## Teknologi

- **Backend**: Flask + Flask-SocketIO
- **Embedding**: `paraphrase-multilingual-MiniLM-L12-v2` (Sentence Transformers)
- **LLM**: `qwen2.5:7b` via Ollama
- **Vector DB**: FAISS
- **PDF Parser**: PyMuPDF

## Instalasi

### Prasyarat

- Python 3.8+
- Ollama terinstall

```bash
# Install Ollama (https://ollama.ai/)
ollama pull qwen2.5:7b
```

### Setup

```bash
# Clone & setup
git clone https://github.com/your-username/RAG-FLASK.git
cd RAG-FLASK
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
./run_script.sh
```

Server berjalan di `http://localhost:9003`

## API Endpoints

### REST API

**Upload Dokumen**
```bash
curl -X POST -F "file=@document.pdf" http://localhost:9003/upload
```

**Tanya Jawab (sync)**
```bash
curl -X POST -H "Content-Type: application/json" \
  -d '{"query": "Siapa pembuat dokumen ini?"}' \
  http://localhost:9003/ask
```

**Health Check**
```bash
curl http://localhost:9003/health
```

### WebSocket API

**Tanya Jawab (streaming)**
```javascript
const socket = io('http://localhost:9003');

socket.emit('ask_stream', {
  query: "Apa isi dokumen?",
  session_id: "unique_id"
});

socket.on('stream_token', (data) => {
  console.log(data.token); // Real-time tokens
});
```

## Cara Kerja

### 1. Indexing Dokumen
```
Upload PDF/TXT → Extract text → Chunking (2000 chars)
→ Embedding → FAISS index
```

### 2. Query Processing
```
Query → Embedding → FAISS search (top-3 chunks)
→ Qwen LLM + context → Streaming answer
```

## Konfigurasi

Edit `app.py` baris 16-33:

```python
CHUNK_SIZE = 2000           # Ukuran chunk (karakter)
CHUNK_OVERLAP = 200         # Overlap antar chunk
OLLAMA_MODEL_NAME = 'qwen2.5:7b'  # Model LLM
EMBEDDING_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
```

## Troubleshooting

**"Ollama not connected"**
```bash
ollama serve
ollama list | grep qwen2.5
```

**"PyTorch error"**
```bash
source venv/bin/activate
pip install -r requirements.txt --upgrade
```

**Konteks tidak relevan**
- Pastikan CHUNK_SIZE cukup besar (min 1000)
- Re-upload dokumen setelah ubah config
- Hapus `documents/*` untuk reset index

## Dokumentasi

- **[CLAUDE.md](CLAUDE.md)** - Arsitektur & development guide
- **[STREAMING_GUIDE.md](STREAMING_GUIDE.md)** - WebSocket streaming detail
- **[PYTORCH_FIX.md](PYTORCH_FIX.md)** - Fix dependency issues

---

Dibuat dengan ❤️
