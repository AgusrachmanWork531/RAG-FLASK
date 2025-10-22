#!/bin/bash

# ====================================
# RAG SERVICE WITH QWEN (OLLAMA) 
# Startup Script
# ====================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  RAG SERVICE STARTUP${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ====================================
# 1. CEK OLLAMA
# ====================================
echo -e "${YELLOW}[1/5] Checking Ollama...${NC}"

if ! command -v ollama &> /dev/null; then
    echo -e "${RED}❌ Ollama tidak terinstall!${NC}"
    echo -e "${YELLOW}Install Ollama terlebih dahulu:${NC}"
    echo -e "   Linux/Mac: curl -fsSL https://ollama.ai/install.sh | sh"
    echo -e "   Windows: Download dari https://ollama.ai"
    exit 1
fi

echo -e "${GREEN}✅ Ollama terinstall${NC}"

# Cek apakah Ollama sedang berjalan
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Ollama tidak berjalan. Memulai Ollama...${NC}"
    
    # Start Ollama di background
    nohup ollama serve > ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo $OLLAMA_PID > ollama.pid
    
    # Tunggu Ollama siap (max 30 detik)
    echo -e "${YELLOW}   Menunggu Ollama siap...${NC}"
    for i in {1..30}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo -e "${GREEN}✅ Ollama berjalan (PID: $OLLAMA_PID)${NC}"
            break
        fi
        sleep 1
        echo -n "."
    done
    echo ""
    
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${RED}❌ Gagal memulai Ollama${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Ollama sudah berjalan${NC}"
fi

# ====================================
# 2. CEK MODEL QWEN
# ====================================
echo -e "\n${YELLOW}[2/5] Checking Qwen model...${NC}"

QWEN_MODEL="qwen2.5:7b"

if ollama list | grep -q "$QWEN_MODEL"; then
    echo -e "${GREEN}✅ Model $QWEN_MODEL tersedia${NC}"
else
    echo -e "${YELLOW}⚠️  Model $QWEN_MODEL belum tersedia${NC}"
    echo -e "${YELLOW}   Downloading model (ini akan memakan waktu)...${NC}"
    
    if ollama pull $QWEN_MODEL; then
        echo -e "${GREEN}✅ Model berhasil didownload${NC}"
    else
        echo -e "${RED}❌ Gagal download model${NC}"
        echo -e "${YELLOW}Alternatif: Gunakan model lebih kecil${NC}"
        echo -e "   Ganti di app.py: OLLAMA_MODEL_NAME = 'qwen2.5:3b'"
        echo -e "   Lalu jalankan: ollama pull qwen2.5:3b"
        exit 1
    fi
fi

# ====================================
# 3. SETUP PYTHON VIRTUAL ENVIRONMENT
# ====================================
echo -e "\n${YELLOW}[3/5] Setting up Python environment...${NC}"

if [ ! -d "venv" ]; then
    echo -e "${YELLOW}   Membuat virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment dibuat${NC}"
fi

# Activate virtual environment
source venv/bin/activate
echo -e "${GREEN}✅ Virtual environment aktif${NC}"

# ====================================
# 4. INSTALL DEPENDENCIES
# ====================================
echo -e "\n${YELLOW}[4/5] Installing dependencies...${NC}"

if [ -f "requirements.txt" ]; then
    pip install --upgrade pip -q
    pip install -r requirements.txt
    echo -e "${GREEN}✅ Dependencies terinstall${NC}"
else
    echo -e "${RED}❌ File requirements.txt tidak ditemukan!${NC}"
    echo -e "${YELLOW}Membuat requirements.txt...${NC}"
    
    cat > requirements.txt << EOF
flask==3.0.0
sentence-transformers==2.2.2
faiss-cpu==1.7.4
PyMuPDF==1.23.8
werkzeug==3.0.1
requests==2.31.0
numpy==1.24.3
torch==2.1.0
EOF
    
    pip install -r requirements.txt
    echo -e "${GREEN}✅ Dependencies terinstall${NC}"
fi

# ====================================
# 5. SETUP DOCUMENTS DIRECTORY
# ====================================
echo -e "\n${YELLOW}[5/5] Checking documents directory...${NC}"

if [ ! -d "documents" ]; then
    mkdir -p documents
    echo -e "${GREEN}✅ Directory 'documents' dibuat${NC}"
    echo -e "${YELLOW}   Tempatkan file .txt atau .pdf di folder 'documents/'${NC}"
else
    DOC_COUNT=$(find documents -type f \( -name "*.txt" -o -name "*.pdf" \) | wc -l)
    echo -e "${GREEN}✅ Directory 'documents' ada ($DOC_COUNT file)${NC}"
fi

# ====================================
# START APPLICATION
# ====================================
echo -e "\n${BLUE}========================================${NC}"
echo -e "${GREEN}🚀 Starting RAG Service...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if app.py exists
if [ ! -f "app.py" ]; then
    echo -e "${RED}❌ File app.py tidak ditemukan!${NC}"
    exit 1
fi

# Jalankan aplikasi
echo -e "${GREEN}Server akan berjalan di: ${BLUE}http://localhost:9003${NC}"
echo -e "${YELLOW}Tekan CTRL+C untuk menghentikan service${NC}"
echo ""
echo -e "${YELLOW}Endpoints:${NC}"
echo -e "  - GET  /health  → Cek status system"
echo -e "  - POST /upload  → Upload dokumen (txt/pdf)"
echo -e "  - POST /ask     → Tanya ke RAG"
echo ""

# Trap CTRL+C untuk cleanup
trap cleanup INT TERM

cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    
    # Kill Ollama jika di-start oleh script ini
    if [ -f "ollama.pid" ]; then
        OLLAMA_PID=$(cat ollama.pid)
        if ps -p $OLLAMA_PID > /dev/null 2>&1; then
            echo -e "${YELLOW}Stopping Ollama (PID: $OLLAMA_PID)...${NC}"
            kill $OLLAMA_PID
            rm ollama.pid
        fi
    fi
    
    echo -e "${GREEN}✅ Service stopped${NC}"
    exit 0
}

# Run the application
python app.py