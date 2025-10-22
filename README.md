

# RAG-FLASK: Aplikasi Tanya Jawab Dokumen dengan LLM

Aplikasi web sederhana yang memungkinkan Anda untuk "berbicara" dengan dokumen Anda. Unggah file PDF atau TXT, dan ajukan pertanyaan tentang isinya. Aplikasi ini menggunakan arsitektur RAG (Retrieval-Augmented Generation) untuk memberikan jawaban yang relevan dan kontekstual berdasarkan dokumen yang Anda berikan.

## Fitur Utama

- **Unggah Dokumen**: Mendukung format file `.pdf` dan `.txt`.
- **Tanya Jawab**: Ajukan pertanyaan dalam bahasa natural dan dapatkan jawaban yang relevan.
- **Model Lokal**: Menggunakan model bahasa (LLM) yang berjalan secara lokal melalui [Ollama](https://ollama.ai/), sehingga data Anda tetap pribadi.
- **Dua Model Andalan**:
    1.  **Model Embedding**: Cepat dan efisien dalam menemukan informasi yang relevan.
    2.  **Model Generatif (LLM)**: Ahli dalam merangkai jawaban yang koheren dan mudah dipahami.
- **API Sederhana**: Dilengkapi dengan endpoint untuk unggah, tanya jawab, dan cek status.

## Diagram Alur Kerja

Aplikasi ini bekerja dalam dua fase utama: **Indeksasi Dokumen** dan **Tanya Jawab (RAG)**.

```mermaid
graph TD
    subgraph "Fase 1: Indeksasi Dokumen (Menyerap Informasi)"
        A[Unggah File PDF/TXT] --> B{Flask App};
        B --> C[Ekstraksi Teks];
        C --> D[Teks dipecah menjadi potongan kecil (Chunks)];
        D --> E[Model Embedding mengubah Chunks menjadi Vektor];
        E --> F[Vektor disimpan dalam Database Vektor (FAISS)];
    end

    subgraph "Fase 2: Proses Tanya Jawab (RAG)"
        G[User Mengajukan Pertanyaan] --> H{Flask App};
        H --> I[Model Embedding mengubah Pertanyaan menjadi Vektor];
        I --> J{Pencarian di Database Vektor};
        J -- Potongan Teks Paling Relevan (Konteks) --> K;
        G -- Pertanyaan Awal --> K;
        K[Model Bahasa (LLM) menerima Pertanyaan + Konteks] --> L[LLM Menghasilkan Jawaban];
        L --> M[Jawaban ditampilkan ke User];
    end

    style F fill:#f9f,stroke:#333,stroke-width:2px
    style J fill:#f9f,stroke:#333,stroke-width:2px
```

## Teknologi yang Digunakan

- **Backend**: [Flask](https://flask.palletsprojects.com/)
- **Arsitektur**: RAG (Retrieval-Augmented Generation)
- **Model Embedding**: `paraphrase-multilingual-MiniLM-L12-v2` (dari [Sentence Transformers](https://www.sbert.net/))
- **Model Bahasa (LLM)**: `qwen2.5:7b` (via [Ollama](https://ollama.ai/))
- **Database Vektor**: [FAISS](https://faiss.ai/) (dari Facebook AI)
- **Ekstraksi PDF**: [PyMuPDF](https://pymupdf.readthedocs.io/)

## Cara Menjalankan

### Prasyarat

1.  **Python 3.8+**
2.  **Ollama Terinstall**: Pastikan Anda sudah menginstall Ollama dan model yang dibutuhkan.
    ```bash
    # Install Ollama (lihat petunjuk di https://ollama.ai/)
    # Tarik model Qwen
    ollama pull qwen2.5:7b
    ```

### Instalasi

1.  **Clone repository ini:**
    ```bash
    git clone https://github.com/your-username/RAG-FLASK.git
    cd RAG-FLASK
    ```

2.  **Buat dan aktifkan virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependensi:**
    ```bash
    pip install -r requirements.txt
    ```

### Menjalankan Aplikasi

1.  **Jalankan server Ollama (di terminal terpisah):**
    ```bash
    ollama serve
    ```
    Biarkan terminal ini tetap berjalan.

2.  **Jalankan aplikasi Flask (di terminal utama):**
    ```bash
    python app.py
    ```

3.  Aplikasi akan berjalan di `http://0.0.0.0:9003`.

## Cara Menggunakan API

Anda bisa menggunakan `curl` atau alat API lainnya untuk berinteraksi dengan aplikasi.

### 1. Unggah Dokumen

Unggah file `CV.pdf` ke dalam folder `documents` untuk diindeks.

- **Endpoint**: `POST /upload`
- **Contoh `curl`**:
  ```bash
  curl -X POST -F "file=@/path/to/your/CV.pdf" http://localhost:9003/upload
  ```

### 2. Ajukan Pertanyaan

Setelah dokumen diindeks, ajukan pertanyaan.

- **Endpoint**: `POST /ask`
- **Contoh `curl`**:
  ```bash
  curl -X POST -H "Content-Type: application/json" \
       -d '{"query": "Apa saja pengalaman kerja yang dimiliki?"}' \
       http://localhost:9003/ask
  ```

### 3. Cek Status Sistem

Memeriksa apakah layanan berjalan dan terhubung ke Ollama.

- **Endpoint**: `GET /health`
- **Contoh `curl`**:
  ```bash
  curl http://localhost:9003/health
  ```

---
Dibuat dengan ❤️ dan Kode

```