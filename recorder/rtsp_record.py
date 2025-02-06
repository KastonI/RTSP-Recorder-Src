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

# 🔧 Налаштування новi
CAM_NUMBER = os.getenv("CAM_NUMBER", "1")

RTSP_URL = f"rtsp://rtsp-to-web:554/id{CAM_NUMBER}/0"
BUFFER_DIR = f"/buffer/cam{CAM_NUMBER}"
CRASH_DIR = f"/crashed/cam{CAM_NUMBER}"
LOG_FILE = f"/var/log/recorder_cam{CAM_NUMBER}.log"
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_UPLOAD_PATH = os.getenv("S3_UPLOAD_PATH", f"crashes/cam{CAM_NUMBER}")
LOG_S3_PATH = os.getenv("LOG_S3_PATH", f"logs/cam{CAM_NUMBER}")

DURATION = int(os.getenv("DURATION", 20))
MAX_BUFFER_SIZE = int(os.getenv("MAX_BUFFER_SIZE", 5))
CHECK_INTERVAL = 10

# 📂 Створюємо необхiднi теки
os.makedirs(BUFFER_DIR, exist_ok=True)
os.makedirs(CRASH_DIR, exist_ok=True)
os.makedirs("/var/log", exist_ok=True)

# 📜 Логування
logging.basicConfig(
    level=logging.INFO,
    format=f"[%(asctime)s] [%(levelname)s] [CAM-{CAM_NUMBER}] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)

logging.info(f"🎥 Камера {CAM_NUMBER} працює з RTSP: {RTSP_URL}")

# 🔍 Налаштування AWS S3
try:
    session = boto3.Session()
    s3 = session.client("s3")
except (BotoCoreError, NoCredentialsError):
    s3 = None  # Вимикаємо S3 якщо не можемо пiдключитись

running = True
recording_active = True
buffer_files = []

# 🔄 Перевiрка потоку
def is_rtsp_available():
    """Перевiрка чи є доступ до потоку"""
    test_command = [
        "ffmpeg", "-rtsp_transport", "tcp", "-i", RTSP_URL,
        "-t", "1", "-c", "copy", "-f", "null", "-"
    ]
    result = subprocess.run(test_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0

# 🛠 Функцiя злиття файлiв
def merge_videos(files, output_file):
    """Об'єднання файлiв перед завантаженням в S3"""
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
            os.remove(file)  # Видаляємо буфернi файли пiсля злиття

# 🛠 Вигрузка файлiв в S3
def upload_crash_to_s3(file_path):
    """Завантажуємо краш-файл в S3 i видаляємо файли"""
    if not s3 or not S3_BUCKET_NAME:
        return

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return

    s3_key = f"{S3_UPLOAD_PATH}/{os.path.basename(file_path)}"

    try:
        s3.upload_file(file_path, S3_BUCKET_NAME, s3_key)
        logging.info(f"🔥 Файл успiшно завантажено в S3: s3://{S3_BUCKET_NAME}/{s3_key}")
        os.remove(file_path)  # Видаляємо файл пiсля завантаження
    except Exception as e:
        logging.error(f"❌ Помилка завантаження у S3: {str(e)}")

# 🕒 Завантаження логiв в S3 кожну годину
def upload_logs_to_s3():
    """Функцiя для завантаження логiв в S3"""
    if not s3 or not S3_BUCKET_NAME:
        return

    try:
        s3_key = f"{LOG_S3_PATH}/recorder_log_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
        s3.upload_file(LOG_FILE, S3_BUCKET_NAME, s3_key)
        logging.info(f"🗂 Логи успiшно завантаженi в S3: s3://{S3_BUCKET_NAME}/{s3_key}")
    except Exception as e:
        logging.error(f"❌ Помилка завантаження логiв в S3: {str(e)}")

    # Повтор через годину
    threading.Timer(3600, upload_logs_to_s3).start()

# Запускаємо фонове завантаження логiв
upload_logs_to_s3()

# 🔄 Основний цикл запису
while running:
    if not is_rtsp_available():
        if recording_active:
            logging.warning("❌ Стрiм втрачено. Починаю обробку краш-файлу...")

            # 🔥 Об'єднання файлiв i вигрузка в S3
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

    logging.info(f"🎥 Запис вiдео: {temp_file}")

    command = [
        "ffmpeg", "-rtsp_transport", "tcp",
        "-i", RTSP_URL, "-t", str(DURATION),
        "-c", "copy", temp_file
    ]

    process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if process.returncode == 0:
        buffer_files.append(temp_file)

    # 🗑 Видалення старих файлiв якщо перевищено лiмiт
    if len(buffer_files) > MAX_BUFFER_SIZE:
        old_file = buffer_files.pop(0)
        os.remove(old_file)
        logging.info(f"🗑 Видалено файл з буферу: {old_file}")

    time.sleep(1)