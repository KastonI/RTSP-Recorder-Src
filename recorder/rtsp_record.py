import os
import time
import datetime
import subprocess
import signal
import sys
import logging
import boto3  # type: ignore
from botocore.exceptions import BotoCoreError, NoCredentialsError

# 🔧 **Конфигурация**
RTSP_URL = os.getenv("RTSP_URL", "rtsp://rtsp-to-web:554/id1/0")
BUFFER_DIR = "/buffer"
CRASH_DIR = "/crashed"
LOG_FILE = "/var/log/recorder.log"
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")  # Имя S3-бакета
S3_UPLOAD_PATH = os.getenv("S3_UPLOAD_PATH", "crashes/cam1/")  # Путь для загрузки краш-файлов в S3

DURATION = int(os.getenv("DURATION", 20))
MAX_BUFFER_SIZE = int(os.getenv("MAX_BUFFER_SIZE", 5))
CHECK_INTERVAL = 10

# 🔹 Создаем папки, если их нет
os.makedirs(BUFFER_DIR, exist_ok=True)
os.makedirs(CRASH_DIR, exist_ok=True)
os.makedirs("/var/log", exist_ok=True)

# 🔍 **Настройка логирования**
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),  # Логи в файл
        logging.StreamHandler(sys.stdout)  # Вывод в консоль
    ],
    force=True  # Принудительное переопределение обработчиков
)

logging.info("🎥 Логирование настроено. Приложение запущено.")

# 🔹 Настройка AWS S3 (без ключей - IAM Role)
try:
    session = boto3.Session()
    s3 = session.client("s3")
    logging.info("✅ AWS S3 клиент инициализирован через IAM Role")
except (BotoCoreError, NoCredentialsError) as e:
    logging.error(f"⚠️ Ошибка инициализации AWS S3: {e}")
    s3 = None  # Если нет доступа, отключаем S3

# Флаг для корректного завершения работы
running = True


# 🔄 **Функция проверки потока**
def is_rtsp_available():
    """Проверяет, доступен ли RTSP-поток"""
    test_command = [
        "ffmpeg", "-rtsp_transport", "tcp", "-i", RTSP_URL,
        "-t", "1", "-c", "copy", "-f", "null", "-"
    ]
    result = subprocess.run(test_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


# 🔄 **Функция обработки завершения**
def cleanup_and_exit(signal_received, frame):
    """Функция корректного завершения работы"""
    global running
    running = False
    logging.info("Остановка записи...")

    if buffer_files:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        merged_file = os.path.join(CRASH_DIR, f"crash_{timestamp}.mp4")
        merge_videos(buffer_files, merged_file)
        logging.info(f"📁 Сохранен аварийный файл перед выходом: {merged_file}")
        upload_crash_to_s3(merged_file)

    for file in buffer_files:
        os.remove(file)

    sys.exit(0)


# 🛠 **Функция склейки видео**
def merge_videos(files, output_file):
    """Объединяет видеофайлы в один"""
    file_list_path = os.path.join(CRASH_DIR, "file_list.txt")

    with open(file_list_path, "w") as file_list:
        for file in files:
            file_list.write(f"file '{file}'\n")

    merge_command = ["ffmpeg", "-f", "concat", "-safe", "0", "-i", file_list_path, "-c", "copy", "-vsync", "vfr", output_file]
    subprocess.run(merge_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# 🛠 **Функция загрузки краш-файлов в S3**
def upload_crash_to_s3(file_path):
    """Загружает краш-файл в S3"""
    if not s3 or not S3_BUCKET_NAME:
        logging.warning("⚠️ S3 не настроен. Файл не будет загружен.")
        return

    try:
        # Используем S3_UPLOAD_PATH
        s3_key = f"{S3_UPLOAD_PATH}{os.path.basename(file_path)}"
        s3.upload_file(file_path, S3_BUCKET_NAME, s3_key)
        logging.info(f"📤 Краш-файл загружен в S3: s3://{S3_BUCKET_NAME}/{s3_key}")

        # После успешной загрузки удаляем локальный файл
        os.remove(file_path)
    except Exception as e:
        logging.error(f"⚠️ Ошибка загрузки в S3: {e}")


# Регистрируем обработчик Ctrl+C
signal.signal(signal.SIGINT, cleanup_and_exit)

# 🔄 **Основной цикл записи**
buffer_files = []
recording_active = True

while running:
    if not is_rtsp_available():
        if recording_active:
            logging.warning("❌ Поток потерян. Жду восстановления...")
            if buffer_files:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                merged_file = os.path.join(CRASH_DIR, f"crash_{timestamp}.mp4")
                merge_videos(buffer_files, merged_file)
                logging.info(f"🔥 Сохранен аварийный файл: {merged_file}")
                upload_crash_to_s3(merged_file)

                for file in buffer_files:
                    os.remove(file)

                buffer_files.clear()

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

    if len(buffer_files) > MAX_BUFFER_SIZE:
        old_file = buffer_files.pop(0)
        os.remove(old_file)
        logging.info(f"🗑 Удален старый файл из кеша: {old_file}")

    # 🔥 Буферные записи НЕ отправляются в S3!

    time.sleep(1)