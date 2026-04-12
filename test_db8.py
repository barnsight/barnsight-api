import asyncio
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from dotenv import load_dotenv
import os

load_dotenv()


async def main():
  mongo_uri = f"mongodb+srv://{os.environ['MONGO_USERNAME']}:{os.environ['MONGO_PASSWORD']}@{os.environ['MONGO_HOSTNAME']}/nosql?authSource=admin"
  client = AsyncMongoClient(mongo_uri)

  db_users = client.users
  api_keys = await db_users.api_keys.find().to_list(None)
  for key in api_keys:
    print("API Key owner_id:", key.get("owner_id"))

  db_events = client.barnsight
  events = await db_events.events.find().to_list(5)
  for event in events:
    print("Event account_id:", event.get("account_id"))


asyncio.run(main())
