import asyncio
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from dotenv import load_dotenv
import os

load_dotenv()


async def main():
  mongo_uri = f"mongodb+srv://{os.environ['MONGO_USERNAME']}:{os.environ['MONGO_PASSWORD']}@{os.environ['MONGO_HOSTNAME']}/nosql?authSource=admin"
  client = AsyncMongoClient(mongo_uri)

  # check users db
  for coll in await client.users.list_collection_names():
    print("users db collection:", coll, "count:", await client.users[coll].count_documents({}))

  # check nosql db
  for coll in await client.nosql.list_collection_names():
    print("nosql db collection:", coll, "count:", await client.nosql[coll].count_documents({}))

  # check barnsight db
  for coll in await client.barnsight.list_collection_names():
    print(
      "barnsight db collection:", coll, "count:", await client.barnsight[coll].count_documents({})
    )


asyncio.run(main())
