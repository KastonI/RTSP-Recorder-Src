import os
import time
import datetime
import subprocess
import signal
import sys
import logging
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
import threading

# Configuration
CAM_NUMBER = os.getenv("CAM_NUMBER", "1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
RECORD_DURATION = int(os.getenv("RECORD_DURATION", 20))
MAX_BUFFER_SIZE = int(os.getenv("MAX_BUFFER_SIZE", 5))

RTSP_URL = f"rtsp://rtsp-to-web:554/id{CAM_NUMBER}/0"
BUFFER_DIR = f"/buffer/cam{CAM_NUMBER}"
CRASH_DIR = f"/crashed/cam{CAM_NUMBER}"
LOG_FILE = f"/var/log/recorder_cam{CAM_NUMBER}.log"
S3_UPLOAD_PATH = f"crashes/cam{CAM_NUMBER}"
LOG_S3_PATH = f"logs/cam{CAM_NUMBER}"

CHECK_INTERVAL = 10

# Creating necessary directories
os.makedirs(BUFFER_DIR, exist_ok=True)
os.makedirs(CRASH_DIR, exist_ok=True)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format=f"[%(asctime)s] [%(levelname)s] [CAM-{CAM_NUMBER}] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)

logging.info(f"🎥 Camera {CAM_NUMBER} is running with RTSP: {RTSP_URL}")

# AWS S3 Configuration
try:
    session = boto3.Session()
    s3 = session.client("s3")
except (BotoCoreError, NoCredentialsError):
    s3 = None  # Disable S3 if connection fails

running = True
recording_active = True
buffer_files = []

#  RTSP Stream Check
def is_rtsp_available():
    """Check if the RTSP stream is available"""
    test_command = [
        "ffmpeg", "-rtsp_transport", "tcp", "-i", RTSP_URL,
        "-t", "1", "-c", "copy", "-f", "null", "-"
    ]
    result = subprocess.run(test_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0

# Video Merging Function
def merge_videos(files, output_file):
    """Merge video files before uploading to S3"""
    if len(files) == 1:
        os.rename(files[0], output_file)
        return

    file_list_path = os.path.join(CRASH_DIR, "file_list.txt")

    with open(file_list_path, "w") as file_list:
        for file in files:
            file_list.write(f"file '{file}'\n")

    merge_command = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", file_list_path, 
        "-c", "copy", "-vsync", "vfr", output_file
    ]
    
    result = subprocess.run(merge_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if result.returncode == 0:
        for file in files:
            os.remove(file)  # Remove buffer files after merging

# Upload Crash Files to S3
def upload_crash_to_s3(file_path):
    """Upload crash file to S3 and delete after upload"""
    if not s3 or not S3_BUCKET_NAME:
        return

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return

    s3_key = f"{S3_UPLOAD_PATH}/{os.path.basename(file_path)}"

    try:
        s3.upload_file(file_path, S3_BUCKET_NAME, s3_key)
        logging.info(f"🔥 File successfully uploaded to S3: s3://{S3_BUCKET_NAME}/{s3_key}")
        os.remove(file_path) # Remove file after upload
    except Exception as e:
        logging.error(f"❌ S3 upload error: {str(e)}")

# Upload logs to S3 every hour
def upload_logs_to_s3():
    """Function to upload logs to S3"""
    if not s3 or not S3_BUCKET_NAME:
        return

    try:
        s3_key = f"{LOG_S3_PATH}/recorder_log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
        s3.upload_file(LOG_FILE, S3_BUCKET_NAME, s3_key)
        logging.info(f"🗂 Logs successfully uploaded to S3: s3://{S3_BUCKET_NAME}/{s3_key}")
    except Exception as e:
        logging.error(f"❌ Log upload error to S3: {str(e)}")

    # Repeat after an hour
    threading.Timer(3600, upload_logs_to_s3).start()

# Start background log upload process
upload_logs_to_s3()

# Main Recording Loop
while running:
    if not is_rtsp_available():
        if recording_active:
            logging.warning("❌ Stream lost. Processing crash file...")

            # Merge files and upload to S3
            if buffer_files:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                merged_file = os.path.join(CRASH_DIR, f"crash_{timestamp}.mp4")
                merge_videos(buffer_files, merged_file)
                upload_crash_to_s3(merged_file)

                buffer_files.clear()

        recording_active = False
        time.sleep(CHECK_INTERVAL)
        continue

    if not recording_active:
        recording_active = True

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    temp_file = os.path.join(BUFFER_DIR, f"{timestamp}.mp4")

    logging.info(f"🎥 Recording video: {temp_file}")

    command = [
        "ffmpeg", "-rtsp_transport", "tcp",
        "-i", RTSP_URL, "-t", str(RECORD_DURATION),
        "-c", "copy", temp_file
    ]

    process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if process.returncode == 0:
        buffer_files.append(temp_file)

    # Delete old files if buffer limit is exceeded
    if len(buffer_files) > MAX_BUFFER_SIZE:
        old_file = buffer_files.pop(0)
        os.remove(old_file)
        logging.info(f"🗑 Removed buffer file: {old_file}")

    time.sleep(1)