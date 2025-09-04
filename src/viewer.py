import pika
import cv2 as cv
import numpy as np
import time
import threading
import queue
from utils import load_config

# --- Config and Setup ---
config = load_config("config/config.yaml")
RABBITMQ_HOST = "localhost"
ANNOTATED_FRAME_QUEUE = config["rabbitmq"]["annotated_frame_queue"]

# A thread-safe queue to hold the most recent frame.
# maxsize=1 means it will only ever hold ONE item, automatically discarding old ones.
frame_buffer = queue.Queue(maxsize=1)


def pika_consumer_thread():
    """This function runs in a separate thread to consume messages from RabbitMQ."""

    def on_frame_received(ch, method, properties, body):
        try:
            # Try to remove whatever is in the buffer
            frame_buffer.get_nowait()
        except queue.Empty:
            # Normal case: buffer was already empty
            pass

        try:
            # Put the new frame into the guaranteed-to-be-empty buffer: ensures the buffer holds most recent frame
            frame_buffer.put_nowait(
                (body, properties)
            )  # Pass properties for the EOS signal
        except queue.Full:
            # For safety
            pass

        ch.basic_ack(delivery_tag=method.delivery_tag)

    # Reconnection loop
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, heartbeat=600)
            )
            channel = connection.channel()
            channel.queue_declare(queue=ANNOTATED_FRAME_QUEUE, durable=True)
            channel.basic_consume(
                queue=ANNOTATED_FRAME_QUEUE,
                on_message_callback=on_frame_received,
                auto_ack=False,
            )

            print(" [*] Pika consumer thread connected. Waiting for annotated frames.")
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            print(
                f"Pika thread could not connect to RabbitMQ: {e}. Retrying in 5 seconds..."
            )
            time.sleep(5)
        except Exception as e:
            print(
                f"An unexpected error occurred in Pika thread: {e}. Retrying in 5 seconds..."
            )
            time.sleep(5)


def main():
    # Start the RabbitMQ consumer in a background thread
    consumer_thread = threading.Thread(target=pika_consumer_thread, daemon=True)
    consumer_thread.start()

    fps_start_time = time.time()
    fps_frame_count = 0
    display_fps = 0

    print("Display loop started. Waiting for first frame...")

    try:
        while True:
            # --- Main Display Loop ---
            try:
                # Get most recent frame from queue.
                latest_frame_body, properties = frame_buffer.get(
                    timeout=1
                )  # Assume the consumer now puts a tuple

                # Check for end-of-stream signal from the headers
                if properties.headers and properties.headers.get("end_of_stream"):
                    print("End-of-stream signal received by viewer. Shutting down.")
                    break

                # Decode frame
                frame = cv.imdecode(
                    np.frombuffer(latest_frame_body, np.uint8), cv.IMREAD_COLOR
                )

                # --- FPS Calculation Logic ---
                fps_frame_count += 1
                elapsed_time = time.time() - fps_start_time
                if elapsed_time > 1.0:
                    display_fps = fps_frame_count / elapsed_time
                    fps_frame_count = 0
                    fps_start_time = time.time()

                cv.putText(
                    frame,
                    f"FPS: {display_fps:.2f}",
                    (frame.shape[1] - 200, frame.shape[0] - 10),
                    cv.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )
                cv.imshow("Live C2 Feed", frame)

            except queue.Empty:
                # Happens if no new frame has arrived in last second.
                print("No new frames received from worker...")
                continue

            if cv.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        cv.destroyAllWindows()
        print("Viewer shut down.")


if __name__ == "__main__":
    main()
