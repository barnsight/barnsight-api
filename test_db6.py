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
  if doc:
    print("URL:", doc.get("image_snapshot"))


asyncio.run(main())
