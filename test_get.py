import requests

res = requests.get("http://localhost:8000/api/v1/events")
print(res.status_code)
if res.status_code == 200:
  events = res.json().get("events", [])
  if events:
    print("Keys:", events[0].keys())
    print("Image URL:", events[0].get("image_snapshot"))
else:
  print(res.text)
