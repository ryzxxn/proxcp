from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
import uuid
import os
import datetime
from jose import jwt

from app.utils.database import get_db, ApiKey, ToolConfigMapping, Tool
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Secret key from environment or fallback
SECRET_KEY = os.getenv("JWT_SECRET", "your_very_long_random_secret_here")
ALGORITHM = "HS256"

# --- Pydantic Models ---

class ApiKeyCreate(BaseModel):
    user_id: str
    name: str

class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    user_id: str
    name: str
    tool_config_id: str
    key: str
    created_at: datetime.datetime
    is_active: bool # <-- UPDATED

    model_config = ConfigDict(from_attributes=True)

class ToolConfigMappingCreate(BaseModel):
    tool_id: uuid.UUID

class ToolConfigMappingResponse(BaseModel):
    id: uuid.UUID
    tool_config_id: str
    tool_id: uuid.UUID
    tool_name: Optional[str] = None
    server_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Routes ---

@router.post("/api_key", response_model=ApiKeyResponse)
def create_api_key(
    request: ApiKeyCreate,
    db: Session = Depends(get_db)
):
    """
    Creates a new API key (JWT token) for the user.
    """
    # Generate a unique tool_config_id
    tool_config_id = str(uuid.uuid4())
    
    # Create the JWT payload
    payload = {
        "user_id": request.user_id,
        "tool_config_id": tool_config_id,
        "type": "api_key",
        "iat": datetime.datetime.utcnow()
        # API keys typically do not expire quickly, you can add 'exp' if needed
    }
    
    # Generate the JWT token
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    # Create database entry
    new_api_key = ApiKey(
        user_id=request.user_id,
        name=request.name,
        tool_config_id=tool_config_id,
        key=token
    )
    
    db.add(new_api_key)
    db.commit()
    db.refresh(new_api_key)
    
    return new_api_key

@router.get("/api_key", response_model=List[ApiKeyResponse])
def list_api_keys(
    user_id: str = Query(..., description="The ID of the user to fetch API keys for"),
    db: Session = Depends(get_db)
):
    """
    Lists all API keys for a user.
    """
    query = select(ApiKey).where(ApiKey.user_id == user_id)
    results = db.execute(query).scalars().all()
    return list(results)

@router.delete("/api_key/{key_id}")
def delete_api_key(
    key_id: uuid.UUID,
    user_id: str = Query(..., description="The ID of the user deleting the API key"),
    db: Session = Depends(get_db)
):
    """
    Deletes an API key.
    """
    query = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    api_key = db.execute(query).scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
        
    db.delete(api_key)
    # Also delete associated mappings
    db.execute(ToolConfigMapping.__table__.delete().where(ToolConfigMapping.tool_config_id == api_key.tool_config_id))
    db.commit()

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": "API key deleted successfully"}

@router.post("/api_key/{key_id}/activate", response_model=ApiKeyResponse)
def toggle_api_key_status(
    key_id: uuid.UUID,
    active: bool = Body(..., embed=True),
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Enables or disables a specific API key.
    """
    query = select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    api_key = db.execute(query).scalar_one_or_none()
    
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
        
    api_key.is_active = active
    db.commit()
    db.refresh(api_key)
    
    logger.info(f"API key {key_id} {'activated' if active else 'deactivated'} for user {user_id}")
    return api_key

# --- Tool Config Mapping Routes ---

@router.get("/api_key/{tool_config_id}/tools", response_model=List[ToolConfigMappingResponse])
def list_api_key_tools(
    tool_config_id: str,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Lists all tools assigned to a specific tool_config_id.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    query = (
        select(ToolConfigMapping, Tool.name, Tool.server_url)
        .outerjoin(Tool, ToolConfigMapping.tool_id == Tool.id)
        .where(ToolConfigMapping.tool_config_id == tool_config_id)
    )
    
    results = db.execute(query).all()
    
    response_list = []
    for mapping, tool_name, server_url in results:
        response_list.append(
            ToolConfigMappingResponse(
                id=mapping.id,
                tool_config_id=mapping.tool_config_id,
                tool_id=mapping.tool_id,
                tool_name=tool_name,
                server_name=server_url # Quick workaround to show something useful
            )
        )
        
    return response_list

@router.post("/api_key/{tool_config_id}/tools", response_model=ToolConfigMappingResponse)
def add_tool_to_api_key(
    tool_config_id: str,
    request: ToolConfigMappingCreate,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Assigns a tool to an API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    # Check if tool exists
    tool = db.execute(select(Tool).where(Tool.id == request.tool_id)).scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Check if mapping already exists
    existing = db.execute(
        select(ToolConfigMapping).where(
            ToolConfigMapping.tool_config_id == tool_config_id, 
            ToolConfigMapping.tool_id == request.tool_id
        )
    ).scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Tool already assigned to this API key")

    new_mapping = ToolConfigMapping(
        tool_config_id=tool_config_id,
        tool_id=request.tool_id
    )
    
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return ToolConfigMappingResponse(
        id=new_mapping.id,
        tool_config_id=new_mapping.tool_config_id,
        tool_id=new_mapping.tool_id,
        tool_name=tool.name,
        server_name=tool.server_url
    )

@router.delete("/api_key/{tool_config_id}/tools/{mapping_id}")
def remove_tool_from_api_key(
    tool_config_id: str,
    mapping_id: uuid.UUID,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Removes a tool from an API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    query = select(ToolConfigMapping).where(ToolConfigMapping.id == mapping_id, ToolConfigMapping.tool_config_id == tool_config_id)
    mapping = db.execute(query).scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
        
    db.delete(mapping)
    db.commit()

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": "Tool removed successfully"}

@router.post("/api_key/{tool_config_id}/sync")
def sync_api_key_tools(
    tool_config_id: str,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Syncs all currently active tools for the user to this API key config.
    Essentially maps all available tools that are not yet mapped.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    # Get all active tools for the user
    tools = db.query(Tool).filter(Tool.user_id == user_id, Tool.is_active == True).all()
    
    # Get existing mappings
    existing_mappings = db.query(ToolConfigMapping).filter(ToolConfigMapping.tool_config_id == tool_config_id).all()
    existing_tool_ids = {m.tool_id for m in existing_mappings}
    
    added_count = 0
    for tool in tools:
        if tool.id not in existing_tool_ids:
            new_mapping = ToolConfigMapping(
                tool_config_id=tool_config_id,
                tool_id=tool.id
            )
            db.add(new_mapping)
            added_count += 1
    
    db.commit()
    logger.info(f"Synced {added_count} new tools to API key config {tool_config_id} for user {user_id}")
    
    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": f"Successfully synced {added_count} new tools to the API key.", "added_count": added_count}
