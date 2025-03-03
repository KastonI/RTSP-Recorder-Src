# **🎬 RTSP Video Recorder & Web Streaming 🎬**  

> This repository contains the source code for the final **DevOps Engineer** project. The full configuration is stored in a separate repository: [Final Project Config](https://github.com/KastonI/final-project-cfg).

---

## **📌 Description**  
📹 **RTSPtoWeb + RTSP Recorder** is a system for **emergency** recording of video streams from IP cameras and streaming them to web browsers.

- **RTSPtoWeb** – a container that captures RTSP streams from surveillance cameras and streams them to a browser (MSE/WebRTC/HLS). It also retransmits the stream to the **RTSP Recorder** container. (Developed by [Deepch](https://github.com/deepch))  
- **RTSP Recorder** – a container running a Python script that monitors the RTSP stream, records it in a buffer, and, in case of a failure, logs the issue and uploads the recorded video up to the moment of failure to **AWS S3**.  

**Docker Compose** is used for deployment.

---

## **📂 File Structure**  

```
.
├── .github/workflows/trigger.yml   # Automated deployment with GitHub Actions
├── recorder/                       # RTSP Recorder service directory
├── rtsptoweb/                      # RTSPtoWeb service directory
├── docker-compose.yaml             # Docker services composition
└── README.md                       # This description file
```

---

## **🚀 Installation and Running**  

For local execution, follow the instructions below. To deploy to the cloud, visit the repository at [Final Project Config](https://github.com/KastonI/final-project-cfg).

### **📥 Clone the Repository**  

```bash
git clone https://github.com/KastonI/final-project-cfg.git
cd final-project-cfg
```

---

### **📎 Required Environment Variables**  

Below are the default values for the required environment variables:

```bash
# AWS Configuration
export AWS_REGION=eu-central-1         # AWS region where the S3 bucket is located
export AWS_ACCESS_KEY_ID=***           # AWS access key for authentication
export AWS_SECRET_ACCESS_KEY=***       # AWS secret key for authentication

# Timezone settings
export TZ=Europe/Warsaw                # Timezone setting for correct timestamp logging

# S3 Configuration
export S3_BUCKET_NAME=your-bucket-name # Name of the AWS S3 bucket where videos and logs will be stored

# Buffer and Recording Settings
export MAX_BUFFER_SIZE=5               # Maximum number of buffered video files before older ones are deleted
export RECORD_DURATION=20              # Duration (in seconds) for each recorded video file

# Camera Configuration
export NUM_CAMERAS=2                   # Number of cameras to be recorded
export RTSP_URL_1=rtsp://login:password@10.10.10.1/  # RTSP URL of the first camera
export RTSP_URL_2=rtsp://login:password@10.10.10.2/  # RTSP URL of the second camera
```

---

### **📦 Running with Docker**  

```bash
docker-compose up -d
```

After startup:

- **RTSPtoWeb** is available at `http://localhost:80`
- **RTSP Recorder** records the stream and uploads videos and logs to **AWS S3** in case of failures.

---

## **⚙️ Configuration**  

### **1. File `docker-compose.yaml`**  

This file defines three containers:

- **rtsp-to-web** – a web service for RTSP streaming.  
- **rtsp-recorder-1** – the first recorder, recording the video stream from Camera 1.  
- **rtsp-recorder-2** – the second recorder, recording the video stream from Camera 2.  

---

### **2. File `recorder/Dockerfile`**  

- Uses `python:3.9-alpine` as the base image.  
- Installs **FFmpeg** and **boto3**.  
- Runs `rtsp_record.py`.  

---

### **3. File `recorder/rtsp_record.py`**  

The main Python script for RTSP video recording:

- Checks if the RTSP stream is available.  
- Saves the video stream to a buffer.  
- If the connection is lost, it uploads the last recorded video file to **AWS S3**.  

---

### **4. File `.github/workflows/trigger.yml`**  

Automated deployment via **GitHub Actions**:

- Runs **Super-Linter** to check the code.  
- If the check passes, it sends a `repository_dispatch` event to **Ansible** (requires a **PAT TOKEN** added to GitHub Actions Secrets).  

---

## **📜 License**  

This project is distributed under the **MIT License**.

> **Authors:**  
> - 📌 **RTSPtoWeb** – [Deepch](https://github.com/deepch)  
> - 📌 **RTSP Recorder** – Developed as part of the `final-project-cfg` project.  
