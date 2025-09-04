import cv2 as cv
import pika
import numpy as np
import logging
import time
import os
import collections
import shutil
import supervision as sv
import json
import base64
import csv
from ultralytics import YOLO
from utils import load_config
import sqlite3

# Load constants from config.yaml file
config = load_config("config/config.yaml")

RABBITMQ_HOST = config["rabbitmq"]["host"]
FRAME_QUEUE = config["rabbitmq"]["frame_queue"]
ANNOTATED_FRAME_QUEUE = config["rabbitmq"]["annotated_frame_queue"]

MODEL_PATH = config["model"]["path"]
CONFIDENCE_THRESHOLD = config["model"]["confidence_threshold"]
IOU_THRESHOLD = config["model"]["iou_threshold"]

SAVE_FRAMES = config["output"]["save_annotated_frames"]
OUT_DIR = config["output"]["frames_dir"]
DB_PATH = config["output"]["database_path"]
LOGS_PATH = config["output"]["logs_path"]

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - WORKER - %(levelname)s - %(message)s"
)

# --- Tracking Setup ---
color = sv.ColorPalette.from_hex(
    ["#ffff00", "#2551E0", "#d1412e", "#ee74b1", "#3cc45a"]
)
box_annotator = sv.BoxAnnotator(color=color, thickness=2)
label_annotator = sv.LabelAnnotator(
    color=color, text_color=sv.Color.BLACK, text_scale=0.4, text_padding=4
)
trace_annotator = sv.TraceAnnotator(color=color, thickness=2, trace_length=100)
tracker = sv.ByteTrack()
smoother = sv.DetectionsSmoother()


def init_db(db_path=DB_PATH):
    """
    Initialize SQLite database and create the tracks table.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS object_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        frame_id INTEGER NOT NULL,
        track_id INTEGER NOT NULL,
        object_class_id INTEGER NOT NULL,
        confidence REAL,
        x_min REAL,
        y_min REAL,
        x_max REAL,
        y_max REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """
    )
    conn.commit()
    conn.close()
    logging.info(f"Database initialized successfully at {db_path}")


def handle_frame(body, properties, model, csv_writer, channel, conn, save_frames=True):
    """
    Processes a single frame: decodes, runs inference, tracks, annotates, and logs.
    """
    # Decode the image
    if properties.headers.get("end_of_stream"):
        logging.info("End-of-stream signal received. Stopping consumer...")
        channel.stop_consuming()
        return

    frame_id = properties.headers.get("frame_id", 0)

    frame = cv.imdecode(np.frombuffer(body, np.uint8), cv.IMREAD_COLOR)

    if frame is None:
        logging.error(f"Failed to decode frame {frame_id}")
        return

    # Run Inference
    inference_start = time.perf_counter()
    results = model.predict(
        frame, conf=CONFIDENCE_THRESHOLD, iou=IOU_THRESHOLD, device="cpu", verbose=False
    )
    inference_time_ms = (time.perf_counter() - inference_start) * 1000

    # Process Detections with Supervision
    detections = sv.Detections.from_ultralytics(results[0])
    tracked_detections = tracker.update_with_detections(detections)
    smoothed_detections = smoother.update_with_detections(tracked_detections)

    # Add detections of the frame to SQLite database
    cursor = conn.cursor()
    for detection in smoothed_detections:
        xyxy, _, confidence, object_class_id, track_id, _ = detection
        x_min, y_min, x_max, y_max = xyxy

        # Insert data in the database
        cursor.execute(
            """
            INSERT INTO object_tracks (frame_id, track_id, object_class_id, confidence, x_min, y_min, x_max, y_max) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                frame_id,
                int(track_id),
                int(object_class_id),
                float(confidence),
                float(x_min),
                float(y_min),
                float(x_max),
                float(y_max),
            ),
        )

    conn.commit()

    # Count detected objects
    object_count = len(smoothed_detections)
    class_counts = collections.Counter(smoothed_detections.class_id)

    # Create Labels for annotation
    labels = [
        f"#{tracker_id} {model.names[class_id]} ({confidence:.2f})"
        for class_id, tracker_id, confidence in zip(
            smoothed_detections.class_id,
            smoothed_detections.tracker_id,
            smoothed_detections.confidence,
        )
    ]

    # Annotate and save the frame
    annotated_frame = box_annotator.annotate(
        scene=frame.copy(), detections=smoothed_detections
    )
    annotated_frame = label_annotator.annotate(
        scene=annotated_frame, detections=smoothed_detections, labels=labels
    )
    annotated_frame = trace_annotator.annotate(
        scene=annotated_frame, detections=smoothed_detections
    )

    # Display frame index and inference time
    label = f"Frame: {frame_id} Inference: {inference_time_ms:.1f}ms"
    cv.putText(
        annotated_frame, label, (20, 40), cv.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2
    )

    # Display the number of objects
    count_breakdown = " | ".join(
        [
            f"{model.names[cls_id]}: {count}"
            for cls_id, count in class_counts.items()
            if count > 0
        ]
    )
    count_label = f"Objects: {count_breakdown}"
    cv.putText(
        annotated_frame,
        count_label,
        (20, 700),
        cv.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 0, 0),
        2,
    )
    
    success, buffer = cv.imencode('.jpg', annotated_frame)
    if success:
        channel.queue_declare(queue=ANNOTATED_FRAME_QUEUE, durable=True)
        channel.basic_publish(
            exchange='',
            routing_key=ANNOTATED_FRAME_QUEUE,
            body=buffer.tobytes(), # Sending raw bytes
        )

    if save_frames:
        out_path = os.path.join(OUT_DIR, f"frame_{int(frame_id):05d}.jpg")
        cv.imwrite(out_path, annotated_frame)

    # Log Metrics
    object_count = len(smoothed_detections)
    csv_writer.writerow([frame_id, inference_time_ms, object_count])
    logging.info(
        f"Processed frame {frame_id}: detections={object_count}, latency={inference_time_ms:.2f}ms"
    )


def main():
    # Initialize the database table if it doesn't exist
    init_db()

    # Initialize connection variables to None
    db_conn = None
    mq_conn = None

    try:
        # Prepare output directories
        os.makedirs(OUT_DIR, exist_ok=True)
        if os.path.exists(OUT_DIR):
            shutil.rmtree(OUT_DIR)
        os.makedirs(OUT_DIR)

        # Open database connection once for the entire session
        db_conn = sqlite3.connect(DB_PATH)
        logging.info("Database connection opened.")

        # Load the YOLO model
        logging.info(f"Loading model from {MODEL_PATH}...")
        model = YOLO(MODEL_PATH)
        logging.info("Model loaded successfully.")

        # Setup RabbitMQ connection
        mq_conn = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=600)
        )
        channel = mq_conn.channel()
        channel.queue_declare(queue=FRAME_QUEUE, durable=True)
        channel.basic_qos(prefetch_count=1)

        # Open the CSV log file for the session
        with open(LOGS_PATH, "w", newline="") as log_file:
            writer = csv.writer(log_file)
            writer.writerow(["frame_id", "inference_time(ms)", "object_count"])

            # Define the callback function
            def callback(ch, method, properties, body):
                try:
                    # Pass the single database connection object to the handler
                    handle_frame(
                        body, properties, model, writer, ch, db_conn, SAVE_FRAMES
                    )
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    frame_id = properties.headers.get("frame_id", "unknown")
                    logging.exception(
                        f"An error occurred while processing frame {frame_id}: {e}"
                    )
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            # Start consuming messages
            channel.basic_consume(queue=FRAME_QUEUE, on_message_callback=callback)
            logging.info(" [*] Waiting for messages. To exit press CTRL+C")
            channel.start_consuming()

    except Exception as e:
        logging.error(
            f"An unexpected error occurred in the main loop: {e}", exc_info=True
        )
    finally:
        # This block ensures resources are always closed gracefully
        if db_conn:
            db_conn.close()
            logging.info("Database connection closed.")
        if mq_conn and mq_conn.is_open:
            mq_conn.close()
            logging.info("RabbitMQ connection closed.")


if __name__ == "__main__":
    main()
