# Используем легковесный Alpine-образ с Python
FROM python:3.9-alpine

# Устанавливаем только необходимые пакеты (FFmpeg + зависимости)
RUN apk add --no-cache ffmpeg py3-pip && \
    pip install --no-cache-dir boto3 && \
    rm -rf /root/.cache

RUN mkdir -p /var/log

# Создаем рабочую директорию
WORKDIR /app

# Копируем скрипт
COPY rtsp_record.py .

# Даем права на выполнение
RUN chmod +x rtsp_record.py

# Открываем порты для RTSP
EXPOSE 554

CMD ["python3", "rtsp_record.py"]
