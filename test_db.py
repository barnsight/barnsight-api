import asyncio
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from dotenv import load_dotenv
import os

load_dotenv()


async def main():
  mongo_uri = f"mongodb+srv://{os.environ['MONGO_USERNAME']}:{os.environ['MONGO_PASSWORD']}@{os.environ['MONGO_HOSTNAME']}/nosql?authSource=admin"
  client = AsyncMongoClient(mongo_uri)
  db = client.barnsight
  doc = await db.events.find_one(sort=[("_id", -1)])
  if not doc:
    print("No events found")
    return
  print("Latest event ID:", doc.get("_id"))
  print("Camera ID:", doc.get("camera_id"))
  print("Has image_snapshot?", "image_snapshot" in doc)
  img = doc.get("image_snapshot")
  if img:
    print("image_snapshot prefix:", img[:50])
  else:
    print("image_snapshot is None or empty")


asyncio.run(main())
