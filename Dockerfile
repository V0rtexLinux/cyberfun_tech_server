FROM python:3.11-slim

# 1. Instalar git, ffmpeg (necessário para pydub) e dependências do scipy
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Instalar pydub + scipy (para os filtros VHS) e eventuais outras libs
RUN pip install --no-cache-dir pydub scipy

# 3. Copiar todo o código (incluindo static/ com a voz_limpa.wav, se existir)
COPY . .

# 4. Criar e configurar o repositório bare
RUN mkdir -p git-server/repo.git && \
    git init --bare git-server/repo.git && \
    git -C git-server/repo.git config http.receivepack true && \
    git -C git-server/repo.git config http.uploadpack true

EXPOSE 5000

# 5. Iniciar o servidor (ele tentará gerar o áudio analog_voice.wav automaticamente na inicialização)
CMD ["python3", "git-server/server.py"]
