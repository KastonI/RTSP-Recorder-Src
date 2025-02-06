# Використовуємо Alpine-образ з Python
FROM python:3.9-alpine

# Iнсталюємо FFmpeg + залежностi wefwe
RUN apk add --no-cache ffmpeg py3-pip && \
    pip install --no-cache-dir boto3 && \
    rm -rf /root/.cache

RUN mkdir -p /var/log

# Робоча директорiя
WORKDIR /app

# Копiюємо скрипт
COPY rtsp_record.py .

# Права на використання
RUN chmod +x rtsp_record.py

# Вiдкриваємо порт для RTSP потоку
EXPOSE 554

CMD ["python3", "rtsp_record.py"]
