import os
import time
import datetime
import subprocess
import signal
import sys
import logging
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

# 🔧 **Настройки**
CAM_NUMBER = os.getenv("CAM_NUMBER", "1")

RTSP_URL = f"rtsp://rtsp-to-web:554/id{CAM_NUMBER}/0"
BUFFER_DIR = f"/buffer/cam{CAM_NUMBER}"
CRASH_DIR = f"/crashed/cam{CAM_NUMBER}"
LOG_FILE = f"/var/log/recorder_cam{CAM_NUMBER}.log"
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
S3_UPLOAD_PATH = os.getenv("S3_UPLOAD_PATH", f"crashes/cam{CAM_NUMBER}/")

DURATION = int(os.getenv("DURATION", 20))
MAX_BUFFER_SIZE = int(os.getenv("MAX_BUFFER_SIZE", 5))
CHECK_INTERVAL = 10

# 📂 Создаём нужные папки
os.makedirs(BUFFER_DIR, exist_ok=True)
os.makedirs(CRASH_DIR, exist_ok=True)
os.makedirs("/var/log", exist_ok=True)

# 📜 **Логирование**
logging.basicConfig(
    level=logging.INFO,
    format=f"[%(asctime)s] [%(levelname)s] [CAM-{CAM_NUMBER}] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ],
    force=True
)

logging.info(f"🎥 Камера {CAM_NUMBER} запущена с RTSP: {RTSP_URL}")
logging.info(f"📤 Запись будет загружаться в: {S3_UPLOAD_PATH}")

# 🔍 **Настройка AWS S3**
try:
    session = boto3.Session()
    s3 = session.client("s3")
    logging.info("✅ AWS S3 клиент инициализирован через IAM Role")
except (BotoCoreError, NoCredentialsError) as e:
    logging.error(f"⚠️ Ошибка инициализации AWS S3: {e}")
    s3 = None  # Отключаем S3, если нет доступа

# 🚦 Флаг для завершения работы
running = True
recording_active = True
buffer_files = []

# 🔄 **Функция проверки потока**
def is_rtsp_available():
    """Проверяет, доступен ли RTSP-поток"""
    test_command = [
        "ffmpeg", "-rtsp_transport", "tcp", "-i", RTSP_URL,
        "-t", "1", "-c", "copy", "-f", "null", "-"
    ]
    result = subprocess.run(test_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0

# 🛠 **Функция слияния видеофайлов**
def merge_videos(files, output_file):
    """Объединяет видеофайлы в один перед загрузкой"""
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
    
    result = subprocess.run(merge_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode == 0:
        logging.info(f"✅ Видео успешно объединено: {output_file}")
        for file in files:
            os.remove(file)  # Удаляем исходные файлы после слияния
    else:
        logging.error(f"❌ Ошибка при объединении файлов. Лог FFmpeg: {result.stderr.decode()}")

# 🛠 **Функция загрузки видеофайлов в S3**
def upload_crash_to_s3(file_path):
    """Загружает краш-файл в S3 и удаляет после успешной отправки"""
    if not s3 or not S3_BUCKET_NAME:
        logging.warning("⚠️ S3 не настроен или переменная S3_BUCKET_NAME пустая.")
        return

    if not os.path.exists(file_path):
        logging.error(f"❌ Ошибка: Файл {file_path} не существует. Пропускаем загрузку.")
        return

    if os.path.getsize(file_path) == 0:
        logging.error(f"❌ Ошибка: Файл {file_path} пустой. Пропускаем загрузку.")
        return

    s3_key = f"{S3_UPLOAD_PATH}/{os.path.basename(file_path)}"

    try:
        logging.info(f"📤 Загружаем {file_path} в S3: s3://{S3_BUCKET_NAME}/{s3_key}")
        s3.upload_file(file_path, S3_BUCKET_NAME, s3_key)
        logging.info(f"✅ Файл успешно загружен в S3: s3://{S3_BUCKET_NAME}/{s3_key}")

        # Удаляем файл после успешной загрузки
        os.remove(file_path)
        logging.info(f"🗑 Локальный файл удалён после загрузки: {file_path}")

    except Exception as e:
        logging.error(f"⚠️ Ошибка загрузки в S3: {e}")

# 🔄 **Основной цикл записи**
while running:
    if not is_rtsp_available():
        if recording_active:
            logging.warning("❌ Поток потерян. Начинаю обработку краша...")

            # 🔥 Объединение и загрузка файлов в S3
            if buffer_files:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                merged_file = os.path.join(CRASH_DIR, f"crash_{timestamp}.mp4")
                merge_videos(buffer_files, merged_file)
                upload_crash_to_s3(merged_file)

                buffer_files.clear()

            logging.warning("⏳ Ожидание восстановления потока...")

        recording_active = False
        time.sleep(CHECK_INTERVAL)
        continue

    if not recording_active:
        logging.info("✅ Поток восстановлен. Возобновляю запись...")
        recording_active = True

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    temp_file = os.path.join(BUFFER_DIR, f"{timestamp}.mp4")

    command = [
        "ffmpeg", "-rtsp_transport", "tcp",
        "-i", RTSP_URL, "-t", str(DURATION),
        "-c", "copy", temp_file
    ]

    logging.info(f"🎥 Запись видео: {temp_file}")
    process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if process.returncode != 0:
        logging.error("❌ Ошибка записи. Жду восстановления потока...")
        continue

    buffer_files.append(temp_file)

    time.sleep(1)

logging.info("🛑 Завершаем процесс RTSP-записи.")