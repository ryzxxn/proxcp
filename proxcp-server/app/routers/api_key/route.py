from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
import uuid
import os
import datetime
import secrets
from jose import jwt

from app.utils.database import (
    get_db, ApiKey, ToolConfigMapping, Tool, 
    ResourceConfigMapping, PromptConfigMapping, Resource, Prompt
)
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

class ResourceConfigMappingCreate(BaseModel):
    resource_id: uuid.UUID

class ResourceConfigMappingResponse(BaseModel):
    id: uuid.UUID
    tool_config_id: str
    resource_id: uuid.UUID
    resource_name: Optional[str] = None
    server_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class PromptConfigMappingCreate(BaseModel):
    prompt_id: uuid.UUID

class PromptConfigMappingResponse(BaseModel):
    id: uuid.UUID
    tool_config_id: str
    prompt_id: uuid.UUID
    prompt_name: Optional[str] = None
    server_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Routes ---

@router.post("/api_key", response_model=ApiKeyResponse)
def create_api_key(
    request: ApiKeyCreate,
    db: Session = Depends(get_db)
):
    """
    Creates a new short, friendly API key (pxp-...) for the user.
    The internal mapping is stored in the database.
    """
    # Generate a unique tool_config_id
    tool_config_id = str(uuid.uuid4())
    
    # Generate a high-entropy short key
    # secrets.token_urlsafe(24) results in ~32 characters
    short_key = f"pxp-{secrets.token_urlsafe(24)}"
    
    # Create database entry
    new_api_key = ApiKey(
        user_id=request.user_id,
        name=request.name,
        tool_config_id=tool_config_id,
        key=short_key
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
    db.execute(ResourceConfigMapping.__table__.delete().where(ResourceConfigMapping.tool_config_id == api_key.tool_config_id))
    db.execute(PromptConfigMapping.__table__.delete().where(PromptConfigMapping.tool_config_id == api_key.tool_config_id))
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

# --- Resource Config Mapping Routes ---

@router.get("/api_key/{tool_config_id}/resources", response_model=List[ResourceConfigMappingResponse])
def list_api_key_resources(
    tool_config_id: str,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Lists all resources assigned to a specific tool_config_id.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    query = (
        select(ResourceConfigMapping, Resource.name, Resource.server_url)
        .outerjoin(Resource, ResourceConfigMapping.resource_id == Resource.id)
        .where(ResourceConfigMapping.tool_config_id == tool_config_id)
    )
    
    results = db.execute(query).all()
    
    response_list = []
    for mapping, resource_name, server_url in results:
        response_list.append(
            ResourceConfigMappingResponse(
                id=mapping.id,
                tool_config_id=mapping.tool_config_id,
                resource_id=mapping.resource_id,
                resource_name=resource_name,
                server_name=server_url
            )
        )
        
    return response_list

@router.post("/api_key/{tool_config_id}/resources", response_model=ResourceConfigMappingResponse)
def add_resource_to_api_key(
    tool_config_id: str,
    request: ResourceConfigMappingCreate,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Assigns a resource to an API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    # Check if resource exists
    resource = db.execute(select(Resource).where(Resource.id == request.resource_id)).scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Check if mapping already exists
    existing = db.execute(
        select(ResourceConfigMapping).where(
            ResourceConfigMapping.tool_config_id == tool_config_id, 
            ResourceConfigMapping.resource_id == request.resource_id
        )
    ).scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Resource already assigned to this API key")

    new_mapping = ResourceConfigMapping(
        tool_config_id=tool_config_id,
        resource_id=request.resource_id
    )
    
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return ResourceConfigMappingResponse(
        id=new_mapping.id,
        tool_config_id=new_mapping.tool_config_id,
        resource_id=new_mapping.resource_id,
        resource_name=resource.name,
        server_name=resource.server_url
    )

@router.delete("/api_key/{tool_config_id}/resources/{mapping_id}")
def remove_resource_from_api_key(
    tool_config_id: str,
    mapping_id: uuid.UUID,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Removes a resource from an API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    query = select(ResourceConfigMapping).where(ResourceConfigMapping.id == mapping_id, ResourceConfigMapping.tool_config_id == tool_config_id)
    mapping = db.execute(query).scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
        
    db.delete(mapping)
    db.commit()

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": "Resource removed successfully"}

# --- Prompt Config Mapping Routes ---

@router.get("/api_key/{tool_config_id}/prompts", response_model=List[PromptConfigMappingResponse])
def list_api_key_prompts(
    tool_config_id: str,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Lists all prompts assigned to a specific tool_config_id.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    query = (
        select(PromptConfigMapping, Prompt.name, Prompt.server_url)
        .outerjoin(Prompt, PromptConfigMapping.prompt_id == Prompt.id)
        .where(PromptConfigMapping.tool_config_id == tool_config_id)
    )
    
    results = db.execute(query).all()
    
    response_list = []
    for mapping, prompt_name, server_url in results:
        response_list.append(
            PromptConfigMappingResponse(
                id=mapping.id,
                tool_config_id=mapping.tool_config_id,
                prompt_id=mapping.prompt_id,
                prompt_name=prompt_name,
                server_name=server_url
            )
        )
        
    return response_list

@router.post("/api_key/{tool_config_id}/prompts", response_model=PromptConfigMappingResponse)
def add_prompt_to_api_key(
    tool_config_id: str,
    request: PromptConfigMappingCreate,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Assigns a prompt to an API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    # Check if prompt exists
    prompt = db.execute(select(Prompt).where(Prompt.id == request.prompt_id)).scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    # Check if mapping already exists
    existing = db.execute(
        select(PromptConfigMapping).where(
            PromptConfigMapping.tool_config_id == tool_config_id, 
            PromptConfigMapping.prompt_id == request.prompt_id
        )
    ).scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Prompt already assigned to this API key")

    new_mapping = PromptConfigMapping(
        tool_config_id=tool_config_id,
        prompt_id=request.prompt_id
    )
    
    db.add(new_mapping)
    db.commit()
    db.refresh(new_mapping)

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return PromptConfigMappingResponse(
        id=new_mapping.id,
        tool_config_id=new_mapping.tool_config_id,
        prompt_id=new_mapping.prompt_id,
        prompt_name=prompt.name,
        server_name=prompt.server_url
    )

@router.delete("/api_key/{tool_config_id}/prompts/{mapping_id}")
def remove_prompt_from_api_key(
    tool_config_id: str,
    mapping_id: uuid.UUID,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Removes a prompt from an API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    query = select(PromptConfigMapping).where(PromptConfigMapping.id == mapping_id, PromptConfigMapping.tool_config_id == tool_config_id)
    mapping = db.execute(query).scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
        
    db.delete(mapping)
    db.commit()

    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": "Prompt removed successfully"}

@router.post("/api_key/{tool_config_id}/resources/sync")
def sync_api_key_resources(
    tool_config_id: str,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Syncs all currently active resources for the user to this API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    # Get all active resources for the user
    resources = db.query(Resource).filter(Resource.user_id == user_id, Resource.is_active == True).all()
    
    # Get existing mappings
    existing_mappings = db.query(ResourceConfigMapping).filter(ResourceConfigMapping.tool_config_id == tool_config_id).all()
    existing_resource_ids = {m.resource_id for m in existing_mappings}
    
    added_count = 0
    for res in resources:
        if res.id not in existing_resource_ids:
            new_mapping = ResourceConfigMapping(
                tool_config_id=tool_config_id,
                resource_id=res.id
            )
            db.add(new_mapping)
            added_count += 1
    
    db.commit()
    logger.info(f"Synced {added_count} new resources to API key config {tool_config_id} for user {user_id}")
    
    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": f"Successfully synced {added_count} new resources to the API key.", "added_count": added_count}

@router.post("/api_key/{tool_config_id}/prompts/sync")
def sync_api_key_prompts(
    tool_config_id: str,
    user_id: str = Query(..., description="The ID of the user"),
    db: Session = Depends(get_db)
):
    """
    Syncs all currently active prompts for the user to this API key config.
    """
    # Verify the user owns this API key
    query_key = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id, ApiKey.user_id == user_id)
    api_key = db.execute(query_key).scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found or unauthorized")

    # Get all active prompts for the user
    prompts = db.query(Prompt).filter(Prompt.user_id == user_id, Prompt.is_active == True).all()
    
    # Get existing mappings
    existing_mappings = db.query(PromptConfigMapping).filter(PromptConfigMapping.tool_config_id == tool_config_id).all()
    existing_prompt_ids = {m.prompt_id for m in existing_mappings}
    
    added_count = 0
    for p in prompts:
        if p.id not in existing_prompt_ids:
            new_mapping = PromptConfigMapping(
                tool_config_id=tool_config_id,
                prompt_id=p.id
            )
            db.add(new_mapping)
            added_count += 1
    
    db.commit()
    logger.info(f"Synced {added_count} new prompts to API key config {tool_config_id} for user {user_id}")
    
    # --- INVALIDATE CACHE ---
    from app.utils.cache import tool_cache
    tool_cache.invalidate(user_id)
    # ------------------------
    
    return {"message": f"Successfully synced {added_count} new prompts to the API key.", "added_count": added_count}
