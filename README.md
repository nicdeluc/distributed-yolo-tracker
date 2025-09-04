# Real-Time Object Tracking & Surveillance Pipeline

![Build Status](https://github.com/YOUR_USERNAME/YOUR_REPO/actions/workflows/ci.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A proof-of-concept distributed system for real-time video analysis. This project simulates a modern Command and Control (C2) or Internet of Military Things (IoMT) data pipeline, capable of ingesting a video stream, performing intelligent object tracking, and making the results available for visualization. The system is built on a robust, message-driven architecture to ensure scalability and resilience.

---

## Live Demo


---

## Key Features
* **Distributed Architecture:** A multi-service system orchestrated with Docker Compose, demonstrating a clean separation of concerns.
* **Asynchronous Messaging:** Uses **RabbitMQ** as a message broker to decouple services, handle backpressure, and ensure data is not lost.
* **AI-Powered Processing:** Performs real-time object detection using a **YOLOv8** model.
* **Stateful Object Tracking:** Implements the **SORT algorithm** to maintain a persistent ID for each detected object across video frames.
* **Data Persistence:** Logs all track data (object ID, class, coordinates, timestamp) to an **SQLite** database for auditing and future analysis.
<!-- * **Edge AI Optimization:** Includes functionality to convert the model to **TensorFlow Lite (INT8 Quantized)**, demonstrating an understanding of performance optimization for edge devices. -->
* **Real-time Viewer:** A local Python viewer subscribes to the results queue to display the annotated video feed live.
* **Headless Video Compiler:** A containerized script to assemble the final annotated frames into a shareable MP4 video file.

---

## System Architecture
The system is designed as a decoupled pipeline with three primary services communicating via a message broker. This design allows for independent scaling and robust error handling.



1.  **Publisher:** This service acts as a sensor feed. It reads frames from a source video, compresses them, and publishes them to the `frame_queue` in RabbitMQ.
2.  **Worker:** The core processing engine. It consumes frames from the `frame_queue`, performs detection and tracking, saves the results to a database, and publishes the final annotated frames to the `results_queue`.
3.  **Viewer/Compiler:** A consumer of the `results_queue`. This can be either the real-time Python viewer running locally or a headless compiler that creates a final video.

---

## Setup & Usage
This project is fully containerized and managed with Docker Compose.

### Prerequisites
* [Docker](https://www.docker.com/get-started)
* [Docker Compose](https://docs.docker.com/compose/install/)

### Configuration
1.  Clone the repository:
    ```bash
    git clone [https://github.com/YOUR_USERNAME/YOUR_REPO.git](https://github.com/YOUR_USERNAME/YOUR_REPO.git)
    cd YOUR_REPO
    ```
2.  Create a `data/` directory for your input video.
    ```bash
    mkdir data
    ```
3.  Place your test video file inside the `data/` directory (e.g., `data/test_video.mp4`).
4.  Copy the example environment file and edit it if necessary.
    ```bash
    cp .env.example .env
    ```

### Running the Application
1.  **Build the Docker images:**
    ```bash
    docker-compose build
    ```
2.  **Launch the main pipeline** (publisher, worker, and message queue):
    ```bash
    docker-compose up publisher worker rabbitmq
    ```
    You will see the logs from the services in your terminal as the video is processed.

### Viewing the Results
You have two options to see the output.

**Option A: Real-Time Viewer (Run while the pipeline is active)**
1.  In a **new, separate terminal**, navigate to the project directory and activate your local Python virtual environment.
2.  Run the viewer script:
    ```bash
    python src/viewer.py
    ```
    A window will pop up showing the live, annotated video feed.

**Option B: Compile the Final Video (Run after the pipeline is finished)**
1.  Once the publisher has finished sending all frames, stop the running services with `Ctrl+C`.
2.  Run the video compiler script as a one-off task:
    ```bash
    docker-compose run --rm worker python src/video_compiler.py
    ```
    The final annotated video will be saved in your `output/` directory.

### Cleaning Up
To stop and remove all containers, run:
```bash
docker-compose down
```

### Project Structure
.
├── src/                  # Main application code
│   ├── worker.py         # AI processing and tracking
│   ├── publisher.py      # Video ingestion
│   ├── viewer.py         # Real-time viewer
│   ├── video_compiler.py # Final video assembly
│   └── db_setup.py       # Database initialization
├── data/                 # Input video files (ignored by Git)
├── .env.example          # Environment variable template
├── docker-compose.yml    # Defines the multi-service application
├── Dockerfile            # Defines the container image for Python services
└── README.md             # This file