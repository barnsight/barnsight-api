# Prompt for Building a Rust Edge Client

*Copy the text below and paste it into a new LLM conversation to generate the Rust edge client.*

---

**System Role:** You are an expert Rust developer specializing in embedded systems, edge AI, and asynchronous programming.

**Objective:** Write a robust, production-ready Rust application that acts as an Edge AI client for the "BarnSight" API. This application will run on a constrained device (like a Raspberry Pi or NVIDIA Jetson) in a barn. It must capture an RTSP camera stream, run object detection using a YOLO model via the ONNX runtime, and communicate asynchronously with a FastAPI backend.

**Core Technology Stack:**
1.  `tokio`: The asynchronous runtime for the application.
2.  `opencv`: Rust bindings for OpenCV to read the RTSP stream and manipulate frames.
3.  `ort`: Rust bindings for ONNX Runtime to perform YOLO object detection locally (free and efficient).
4.  `reqwest`: Async HTTP client for interacting with the BarnSight API.
5.  `serde` & `serde_json`: For JSON serialization/deserialization.
6.  `base64`: For encoding image snapshots before uploading.
7.  `dotenvy`: For loading configuration from a `.env` file.
8.  `tracing` & `tracing-subscriber`: For structured, production-grade logging.

**Application Architecture & Concurrency Rules:**
*   **Initialization:** Load environment variables (`API_URL`, `API_KEY`, `RTSP_URL`, `CAMERA_ID`, `DEVICE_ID`, `YOLO_ONNX_PATH`, `CONFIDENCE_THRESHOLD`). Initialize the `tracing` logger.
*   **Heartbeat Task (Tokio Spawn):**
    *   Create an infinite async loop that runs in the background.
    *   Every **4 minutes** (to stay safely under a 5-minute Redis TTL on the server), send an empty `POST` request to `[API_URL]/api/v1/devices/heartbeat`.
    *   Include the header: `X-API-Key: [API_KEY]`.
    *   If the request fails (e.g., network drop), log a warning but **do not panic** or crash the task. It should retry on the next interval.
*   **Main Inference Loop:**
    *   Open the RTSP stream using `opencv::videoio::VideoCapture`.
    *   Continuously read frames. To save CPU, only pass every Nth frame (e.g., every 15th frame for ~2 FPS processing on a 30 FPS stream) to the `ort` inference engine.
    *   Run the frame through the YOLO ONNX model.
*   **Event Uploading (Non-Blocking):**
    *   If a detection occurs (specifically looking for the class representing "manure") and the confidence is greater than `CONFIDENCE_THRESHOLD` (e.g., `0.5`):
        1.  Extract the bounding box (normalized or absolute, but map it to `x`, `y`, `width`, `height`).
        2.  Encode the original frame (or a cropped version) to a JPEG format in memory using OpenCV's `imencode`, then encode that buffer to a Base64 string.
        3.  Construct the `EventCreate` JSON payload (schema below).
        4.  **Crucially:** Spawn a new asynchronous Tokio task to send the `POST` request to `[API_URL]/api/v1/events` (with the `X-API-Key` header). **The main OpenCV frame-reading loop must never block waiting for the HTTP upload to finish.**

**JSON Payload Schema for `/api/v1/events`:**
```json
{
  "timestamp": "2026-04-09T12:00:00Z", // Must be UTC ISO8601 format
  "camera_id": "cam_01",
  "device_id": "edge_pi_01",
  "confidence": 0.85,
  "bounding_box": {
    "x": 100.5,
    "y": 200.0,
    "width": 50.0,
    "height": 50.0
  },
  "image_snapshot": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ..." // Optional, but required for this implementation
}
```

**Deliverables Required in Your Response:**
1.  The `Cargo.toml` file with all necessary dependencies and their recommended versions.
2.  The complete, well-commented `src/main.rs` file demonstrating the architecture described above.
3.  Ensure you include a mock or simplified version of the ONNX/YOLO processing step if full YOLO post-processing (NMS, box decoding) is too verbose, but clearly mark where the inference happens and how the resulting bounding box triggers the upload.
4.  A sample `.env` file.

**Constraints:**
*   The code must compile.
*   Prioritize memory safety and robust error handling (no `.unwrap()` or `.expect()` in the main loops that could cause a panic if the camera feed drops).

---