FROM python:3.9-alpine

# Install FFmpeg + dependencies
RUN apk add --no-cache ffmpeg py3-pip && \
    pip install --no-cache-dir boto3 && \
    rm -rf /root/.cache

# Create log directory
RUN mkdir -p /var/log

# Set working directory
WORKDIR /app

# Copy script
COPY rtsp_record.py .

# Set permissions
RUN chmod +x rtsp_record.py

# Expose the port for the RTSP stream
EXPOSE 554

# Run rtsp_record.py
CMD ["python3", "rtsp_record.py"]