from typing import Annotated, Optional
from fastapi import Request, Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from core.database import MongoClient
from crud.api_key_crud import ApiKeyCRUD

# Define the header for API keys
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_mongo_client():
    from core.database import MongoClient
    if not MongoClient._client:
        await MongoClient.connect()
    return MongoClient._client

async def validate_api_key(
    request: Request,
    api_key: Optional[str] = Depends(api_key_header),
    mongo: MongoClient = Depends(get_mongo_client)
):
    """
    Dependency to validate API keys from the request header.
    Can be used alongside or instead of JWT auth.
    """
    if not api_key:
        return None
    
    db = mongo.get_database("users")
    api_key_crud = ApiKeyCRUD(db)
    
    key_doc = await api_key_crud.validate_key(api_key)
    if not key_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    
    # Store the account/owner info in the request state
    request.state.api_key_owner = key_doc.get("owner_id")
    return key_doc
