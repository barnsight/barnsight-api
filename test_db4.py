import asyncio
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from dotenv import load_dotenv
import os

load_dotenv()


async def main():
  mongo_uri = f"mongodb+srv://{os.environ['MONGO_USERNAME']}:{os.environ['MONGO_PASSWORD']}@{os.environ['MONGO_HOSTNAME']}/nosql?authSource=admin"
  client = AsyncMongoClient(mongo_uri)
  db = client.barnsight

  docs = await db.events.find().sort("_id", -1).limit(5).to_list(None)
  for doc in docs:
    print(
      "Event:",
      doc.get("_id"),
      "Camera:",
      doc.get("camera_id"),
      "Has image?",
      bool(doc.get("image_snapshot")),
    )


asyncio.run(main())
