import requests

res = requests.post(
  "http://localhost:8000/api/v1/auth/login",
  data={"username": "th0truth", "password": "GOq5fMxLyxE9SQpo"},
)
print(res.status_code, res.text)
if res.status_code == 200:
  token = res.json()["access_token"]
  res2 = requests.get(
    "http://localhost:8000/api/v1/events", headers={"Authorization": f"Bearer {token}"}
  )
  print(res2.status_code, res2.text[:200])
