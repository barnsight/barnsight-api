import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.get_database("test_db")
    await db.events.drop()
    
    # Test empty collection
    pipeline = [{"$match": {}}, {"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence"}}}]
    res = await db.events.aggregate(pipeline).to_list(None)
    print("Empty collection:", res)

    # Test collection with documents but no confidence
    await db.events.insert_one({"some_field": 1})
    res = await db.events.aggregate(pipeline).to_list(None)
    print("Documents but no confidence:", res)

asyncio.run(main())
