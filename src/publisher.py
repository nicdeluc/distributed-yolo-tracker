import cv2 as cv
import pika
import logging
from utils import load_config


def publish_video(video_path, rabbitmq_host):
    """
    Connects to RabbitMQ, reads frames from a video, and publishes them.
    """
    try:
        # Establish a connection with RabbitMQ server
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=rabbitmq_host)
        )
        channel = connection.channel()
        logging.info("Successfully connected to RabbitMQ.")

    except pika.exceptions.AMQPConnectionError as e:  # type: ignore
        logging.error(f"Failed to connect to RabbitMQ at {rabbitmq_host}: {e}")
        return

    # Declare a durable queue named "frame_queue"
    queue_name = "frame_queue"
    channel.queue_declare(queue=queue_name, durable=True)
    logging.info(f"Declared queue '{queue_name}'.")

    cap = cv.VideoCapture(video_path)
    if not cap.isOpened():
        logging.error(f"Error opening video file: {video_path}")
        return

    logging.info(f"Started publishing frames from {video_path}...")
    frame_id = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Encode frame as JPEG for efficient network transfer
        result, encoded_image = cv.imencode(".jpg", frame)
        if not result:
            logging.warning("Failed to encode frame.")
            continue

        # Create a headers dictionary for metadata (frame id)
        headers = {"frame_id": frame_id}

        # Publish the raw JPEG bytes as the body, and the metadata in headers
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=encoded_image.tobytes(),  # Send the raw bytes
            properties=pika.BasicProperties(
                delivery_mode=2, headers=headers  # <-- Add your metadata here
            ),
        )
        frame_id += 1

    # Send a special "end of stream" message with a header
    logging.info("Publishing end-of-stream signal.")
    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=b"",  # Empty body
        properties=pika.BasicProperties(
            delivery_mode=2, headers={"end_of_stream": True}
        ),
    )
    logging.info("Finished publishing all frames.")
    cap.release()
    connection.close()


def main():
    # --- Load Config ---
    config = load_config("config/config.yaml")
    VIDEO_PATH = config["data"]["video_path"]
    RABBITMQ_HOST = config["rabbitmq"]["host"]

    # --- Logging Setup ---
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - WORKER - %(levelname)s - %(message)s"
    )

    publish_video(VIDEO_PATH, RABBITMQ_HOST)


if __name__ == "__main__":
    main()
