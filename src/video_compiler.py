import cv2
import os
import logging
from tqdm.auto import tqdm
from utils import load_config


# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - COMPILER - %(levelname)s - %(message)s"
)


def get_fps(video_path):
    """Gets the FPS of the original video."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logging.error(f"Could not open video at {video_path} to get FPS.")
        return None
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps


def compile_video(
    fps=30.0, frames_dir="output/frames", output_path="output/annotated_video.mp4"
):
    """
    Uses OpenCV's VideoWriter to compile annotated frames into a video.
    """
    print("\nStarting video compilation...")

    # Check if the frame directory exists
    if not os.path.isdir(frames_dir):
        logging.error(f"Frames directory not found at: {frames_dir}")
        return

    try:
        # Get a sorted list of frame image files
        frame_files = sorted([f for f in os.listdir(frames_dir) if f.endswith(".jpg")])
        if not frame_files:
            logging.error("No frame images found in the directory.")
            return

        # Read the first frame to get the dimensions (width, height)
        first_frame_path = os.path.join(frames_dir, frame_files[0])
        frame = cv2.imread(first_frame_path)
        height, width, _ = frame.shape

        # Define video codec ('mp4v') and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        # Loop through all the frames and write them to the video
        for frame_file in tqdm(frame_files, desc="Compiling", unit="frame"):
            frame_path = os.path.join(frames_dir, frame_file)
            img = cv2.imread(frame_path)
            out.write(img)

        # Release the VideoWriter to finalize the video
        out.release()
        logging.info(f"Video compilation successful! Saved to {output_path}")

    except Exception as e:
        print(f"\nAn error occurred during video compilation: {e}")


def main():
    config = load_config("config/config.yaml")
    video_path = config["data"]["video_path"]
    frames_dir = config["output"]["frames_dir"]

    # Get the original FPS for smooth playback
    fps = get_fps(video_path)
    if fps is None:
        logging.warning(
            "Could not determine original FPS. Using default value of 30.0."
        )
        fps = 30.0
    else:
        logging.info(f"Using original video FPS for compilation: {fps:.2f} FPS")

    # Compile the video
    compile_video(fps, frames_dir)


if __name__ == "__main__":
    main()
