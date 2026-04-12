import asyncio
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from dotenv import load_dotenv
import os

load_dotenv()


async def main():
  mongo_uri = f"mongodb+srv://{os.environ['MONGO_USERNAME']}:{os.environ['MONGO_PASSWORD']}@{os.environ['MONGO_HOSTNAME']}/nosql?authSource=admin"
  client = AsyncMongoClient(mongo_uri)
  db = client.nosql
  doc = await db.events.find_one(sort=[("_id", -1)])
  if not doc:
    print("No events found in nosql.events")
  else:
    print("Found event in nosql.events:", doc.get("_id"))
  db_users = client.users
  user = await db_users.users.find_one()
  if user:
    print("Found user in users.users")


asyncio.run(main())
