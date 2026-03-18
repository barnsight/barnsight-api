from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class ApiKeyCreate(BaseModel):
    name: str = Field(..., description="A friendly name for the API key (e.g., 'Barn 1 Edge Device')")
    expires_in_days: Optional[int] = Field(None, description="Optional expiration in days")

class ApiKeyResponse(BaseModel):
    key: str = Field(..., description="The actual API key (only shown once during creation)")
    name: str
    created_at: datetime
    id: str = Field(..., alias="_id")

    class Config:
        populate_by_name = True

class ApiKeyInDB(BaseModel):
    hashed_key: str
    owner_id: str
    name: str
    created_at: datetime
    last_used: Optional[datetime] = None
