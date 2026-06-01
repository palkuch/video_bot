FROM python:3.11-slim

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем свежий yt-dlp + зависимости для JS-челленджей
RUN pip install --no-cache-dir \
    python-telegram-bot \
    "yt-dlp[default]" \
    && npm install -g jsdom

WORKDIR /app
COPY . .

# Права на файлы
RUN chmod 644 cookies.txt 2>/dev/null || true

CMD ["python3", "video_bot_1.py"]
