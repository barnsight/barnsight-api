import requests
import datetime

payload = {
  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "camera_id": "test_cam",
  "confidence": 0.99,
  "bounding_box": {"x": 1, "y": 1, "width": 10, "height": 10},
  "image_snapshot": "data:image/jpeg;base64,/9j/4AAQSkZJRgAB",
}
# wait we need an API key to test
