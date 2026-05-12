import logging
import asyncio
import json
import time # <-- ADDED
import datetime # <-- ADDED
from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
import uuid  # <-- ADDED

# --- Imports for FastAPI Router ---
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl, ConfigDict
from sqlalchemy.orm import Session

# --- Imports for ServerManager Logic ---
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
# --- (MODIFIED) Import all required DB models ---
from app.utils.database import get_db, Tool, Transaction, UserServerConfig, get_db_context
from app.utils.network import rewrite_docker_url
from app.utils.connections import connection_manager
from app.utils.track import log_transaction # <-- ADDED

# Configure logging
logger = logging.getLogger(__name__)

class ServerManager:
    """Manages server tools for multiple users, storing each tool as an individual row."""
    def __init__(self):
        self._lock = asyncio.Lock()

    async def connect_servers(
        self,
        urls_with_auth: List['ServerAuth'],
        user_id: str,
        force_refresh: bool = False,
        retries: int = 3,
        backoff: float = 0.5
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch tools from DB or servers. Stores each tool in its own row.
        Use force_refresh=True to update cache.
        Processes servers in parallel for better performance.
        """
        async def sync_one(server_auth: 'ServerAuth'):
            url = str(server_auth.url)
            token = server_auth.token
            with get_db_context() as db:
                db_tools = None
                try:
                    # 1. Check database for active tools, unless refresh is forced
                    if not force_refresh:
                        db_tools = db.query(Tool).filter(
                            Tool.user_id == user_id,
                            Tool.server_url == url,
                            Tool.is_active == True
                        ).all()
                        
                        if db_tools:
                            if db_tools[0].server_token == token:
                                tools_list = [json.loads(tool.definition) for tool in db_tools]
                                logger.info(f"Cache hit: Retrieved {len(tools_list)} active tools from DB for user {user_id} at {url}")
                                return url, {"status": "success", "tools": tools_list}
                            else:
                                logger.info(f"Token changed for {url}. Forcing refresh.")
                except Exception as e:
                    logger.warning(f"Database cache check failed for {url}: {e}")

                # 2. Fetch tools from the server
                for attempt in range(retries):
                    try:
                        client = await connection_manager.get_client(url, token)
                        fetched_tools = await client.list_tools()
                        tools_list = self._convert_tools(fetched_tools, url)

                        if not tools_list:
                            # ... (rest of the logic for no tools)
                            if force_refresh or not db_tools:
                                db.query(Tool).filter(
                                    Tool.user_id == user_id,
                                    Tool.server_url == url
                                ).update({"is_active": False})
                                db.commit()
                            return url, {"status": "success", "tools": []}
                        
                        existing_db_tools = {
                            t.name: t for t in db.query(Tool).filter(
                                Tool.user_id == user_id,
                                Tool.server_url == url
                            ).all()
                        }

                        seen_tool_names = set()
                        for tool_schema in tools_list:
                            tool_name = tool_schema.get("name")
                            if not tool_name: continue
                            seen_tool_names.add(tool_name)
                            
                            if tool_name in existing_db_tools:
                                db_tool = existing_db_tools[tool_name]
                                db_tool.definition = json.dumps(tool_schema)
                                db_tool.is_active = True
                                db_tool.server_token = token
                            else:
                                db_tool = Tool(
                                    user_id=user_id,
                                    name=tool_name,
                                    definition=json.dumps(tool_schema),
                                    server_url=url,
                                    is_active=True,
                                    server_token=token
                                )
                                db.add(db_tool)
                        
                        for name, tool in existing_db_tools.items():
                            if name not in seen_tool_names:
                                tool.is_active = False
                        
                        db.commit()
                        logger.info(f"Successfully synced {len(tools_list)} tools from {url} for user {user_id}")
                        return url, {"status": "success", "tools": tools_list}
                    except Exception as e:
                        # Clear dead client from manager
                        await connection_manager.remove_client(url, token)
                        
                        if attempt < retries - 1:
                            logger.warning(f"Retry {attempt+1}/{retries} for {url}: {e}")
                            await asyncio.sleep(backoff * (2 ** attempt))
                        else:
                            logger.error(f"Failed to connect to {url} for user {user_id} after {retries} attempts: {e}")
                            return url, {"status": "error", "message": str(e)}

        # Run all synchronizations in parallel
        tasks = [sync_one(sa) for sa in urls_with_auth]
        completed_results = await asyncio.gather(*tasks)
        
        # Filter out None results to avoid dict() constructor error
        valid_results = [r for r in completed_results if r is not None]
        return {"results": dict(valid_results)}

    def _convert_tools(self, tools: List[Any], url: str) -> List[Dict[str, Any]]:
        """Convert tools to dictionaries and add server_url."""
        # (This method is unchanged)
        tools_list = []
        for tool in tools:
            try:
                if isinstance(tool, dict):
                    tool_dict = tool
                elif hasattr(tool, 'to_dict') and callable(tool.to_dict):
                    tool_dict = tool.to_dict()
                elif hasattr(tool, '__dict__'):
                    tool_dict = vars(tool)
                else:
                    logger.warning(f"Skipping tool that cannot be converted to dict: {tool}")
                    continue

                if "name" not in tool_dict:
                    logger.warning(f"Skipping tool with missing name from {url}: {tool_dict}")
                    continue

                tool_dict["server_url"] = url
                tools_list.append(tool_dict)
            except Exception as e:
                logger.warning(f"Skipping invalid tool from {url}: {tool} (failed to convert: {e})")
        return tools_list

    async def call_server_method(
        self,
        url: str,
        method_name: str,
        user_id: str,
        session_id: str,
        **kwargs
    ) -> Any:
        """
        Call a tool on a server, logging the transaction.
        Retrieves the saved token from the DB for the call.
        """
        with get_db_context() as db:
            server_name = urlparse(url).netloc.replace(":", "_")

            transaction = Transaction(
                user_id=user_id,
                session_id=session_id,
                server_name=server_name,
                jsonrpc_method=method_name,
                request_params=json.dumps(kwargs),
                status="accepted",
                tool_name=method_name
            )
            db.add(transaction)
            db.commit()
            db.refresh(transaction)

            try:
                # Security check: Get the tool and its token
                tool = db.query(Tool).filter(
                    Tool.user_id == user_id,
                    Tool.server_url == url,
                    Tool.name == method_name,
                    Tool.is_active == True
                ).first()

                if not tool:
                    logger.warning(f"Security check failed: Active tool '{method_name}' from '{url}' not found for user '{user_id}'")
                    raise ValueError(f"Method '{method_name}' not available, not active, or not found for user '{user_id}' at server '{url}'")

                # --- (SIMPLIFIED) ---
                token = tool.server_token
                
                # Use persistent connection manager
                client = await connection_manager.get_client(url, token)
                result = await client.call_tool(method_name, kwargs)

                transaction.status = "completed"
                # Storing result.data if it exists, otherwise the raw result
                result_to_store = result.data if hasattr(result, 'data') else result
                # Avoid storing massive data blobs if not simple types
                if isinstance(result_to_store, (str, int, float, bool, dict, list, type(None))):
                    transaction.response_data = json.dumps(result_to_store)
                else:
                    transaction.response_data = json.dumps({"type": str(type(result_to_store)), "message": "Result is a complex object, not stored."})
                
                db.commit()

                return result.data if hasattr(result, 'data') else result

            except Exception as e:
                transaction.status = "failed"
                transaction.response_data = json.dumps({"error": str(e)})
                db.commit()
                logger.error(f"Error calling {method_name} for user {user_id} at {url}: {e}", exc_info=True)
                raise RuntimeError(f"Server-side call to '{method_name}' failed: {e}")

    async def close(self, user_id: Optional[str] = None):
        """Clear tools from database for a specific user or all users."""
        async with self._lock:
            with get_db_context() as db:
                query = db.query(Tool)
                if user_id:
                    query = query.filter(Tool.user_id == user_id)
                    logger.info(f"Clearing tools for user {user_id} from database")
                else:
                    logger.info("Clearing all tools from database")
                query.delete()
                db.commit()

# --- Singleton instance ---
server_manager = ServerManager()

# ----------------------------------------------------------------------
# --- FastAPI Router ---
# ----------------------------------------------------------------------

router = APIRouter()

# --- Pydantic Models for Request/Response ---

class ServerAuth(BaseModel):
    """Defines the server URL and its associated auth token."""
    url: HttpUrl
    token: Optional[str] = None

# --- (NEW) Pydantic Models for ServerConfig CRUD ---

class ServerConfigBase(BaseModel):
    """Base model for server config properties."""
    url: HttpUrl
    token: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = True

class ServerConfigCreate(ServerConfigBase):
    """Model for creating a new server config."""
    pass

class ServerConfigUpdate(ServerConfigBase):
    """Model for updating an existing server config."""
    pass

class ServerConfig(ServerConfigBase):
    """Model for representing a server config in the DB (response model)."""
    id: uuid.UUID
    user_id: str
    
    model_config = ConfigDict(from_attributes=True)

class SyncResponse(BaseModel):
    """Response body model for the synchronize endpoint."""
    results: Dict[str, Dict[str, Any]]


# --- (NEW) ServerConfig CRUD Endpoints ---

@router.post(
    "/{user_id}/servers",
    response_model=ServerConfig,
    summary="Add a New Server Configuration",
    description="Adds a new server URL and token to the user's configuration list."
)
async def add_server_config(
    user_id: str,
    config: ServerConfigCreate,
    db: Session = Depends(get_db)
):
    """
    Adds a new server configuration to the database for the specified user.
    """
    try:
        # Check if this exact URL already exists for this user
        existing_config = db.query(UserServerConfig).filter(
            UserServerConfig.user_id == user_id,
            UserServerConfig.url == str(config.url)
        ).first()
        
        if existing_config:
            raise HTTPException(
                status_code=409, 
                detail=f"Server configuration with URL '{config.url}' already exists."
            )

        db_config = UserServerConfig(
            user_id=user_id,
            name=config.name,
            url=str(config.url),
            token=config.token,
            is_active=config.is_active
        )
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        logger.info(f"Added new server config ID {db_config.id} for user {user_id} at {db_config.url}")

        # --- INVALIDATE CACHE ---
        from app.utils.cache import tool_cache
        tool_cache.invalidate(user_id)
        # ------------------------

        # --- (AUTO-SYNC) ---
        try:
            if db_config.is_active:
                await server_manager.connect_servers(
                    urls_with_auth=[ServerAuth(url=db_config.url, token=db_config.token)],
                    user_id=user_id,
                    force_refresh=True
                )
                logger.info(f"Auto-synced tools for new server {db_config.url}")
        except Exception as sync_err:
            logger.warning(f"Auto-sync failed for new server {db_config.url}: {sync_err}")
        # ------------------

        return db_config
    except HTTPException:
        raise # Re-raise HTTPException
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to add server config for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.get(
    "/{user_id}/servers",
    response_model=List[ServerConfig],
    summary="List All Server Configurations",
    description="Retrieves all server configurations for the specified user."
)
async def list_server_configs(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    Retrieves a list of all server configurations for the given user.
    """
    db_configs = db.query(UserServerConfig).filter(UserServerConfig.user_id == user_id).all()
    return db_configs

@router.put(
    "/{user_id}/servers/{server_id}",
    response_model=ServerConfig,
    summary="Update a Server Configuration",
    description="Updates the details of a specific server configuration."
)
async def update_server_config(
    user_id: str,
    server_id: uuid.UUID,  # <-- FIX 2: Changed from int to uuid.UUID
    config: ServerConfigUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates an existing server configuration (URL, token, name, active status).
    """
    db_config = db.query(UserServerConfig).filter(
        UserServerConfig.id == server_id,
        UserServerConfig.user_id == user_id
    ).first()

    if not db_config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")
    
    old_url = db_config.url
    new_url = str(config.url)
    
    # Update fields from the request model
    db_config.name = config.name
    db_config.url = new_url
    db_config.token = config.token
    db_config.is_active = config.is_active

    try:
        # If URL changed, we must update all associated tools
        if old_url != new_url:
            db.query(Tool).filter(
                Tool.user_id == user_id,
                Tool.server_url == old_url
            ).update({
                Tool.server_url: new_url,
                Tool.server_token: config.token # Also update token
            })
            logger.info(f"Updated associated tools from {old_url} to {new_url} for user {user_id}")

        db.commit()
        db.refresh(db_config)
        logger.info(f"Updated server config ID {db_config.id} for user {user_id}")

        # --- INVALIDATE CACHE ---
        from app.utils.cache import tool_cache
        tool_cache.invalidate(user_id)
        # ------------------------

        # --- (AUTO-SYNC) ---
        try:
            if db_config.is_active:
                await server_manager.connect_servers(
                    urls_with_auth=[ServerAuth(url=db_config.url, token=db_config.token)],
                    user_id=user_id,
                    force_refresh=True
                )
                logger.info(f"Auto-synced tools for updated server {db_config.url}")
                # If deactivated, we might want to clear its tools
                tools_to_delete = db.query(Tool).filter(
                    Tool.user_id == user_id,
                    Tool.server_url == db_config.url
                ).all()
                tool_ids = [t.id for t in tools_to_delete]
                
                if tool_ids:
                    from app.utils.database import ToolConfigMapping
                    db.query(ToolConfigMapping).filter(
                        ToolConfigMapping.tool_id.in_(tool_ids)
                    ).delete(synchronize_session=False)
                
                for t in tools_to_delete:
                    db.delete(t)
                
                db.commit()
                logger.info(f"Deactivated server {db_config.url}, cleared tools and mappings.")
        except Exception as sync_err:
            logger.warning(f"Auto-sync failed for updated server {db_config.url}: {sync_err}")
        # ------------------

        return db_config
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update server config {server_id} for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

@router.delete(
    "/{user_id}/servers/{server_id}",
    response_model=Dict[str, str],
    summary="Delete a Server Configuration",
    description="Deletes a server configuration and all associated tools from the database."
)
async def delete_server_config(
    user_id: str,
    server_id: uuid.UUID,  # <-- FIX 3: Changed from int to uuid.UUID
    db: Session = Depends(get_db)
):
    """
    Deletes a server configuration.
    This will also delete all associated tools for this user from that server.
    """
    db_config = db.query(UserServerConfig).filter(
        UserServerConfig.id == server_id,
        UserServerConfig.user_id == user_id
    ).first()

    if not db_config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")
    
    try:
        server_url = db_config.url
        
        # 1. Delete the server config itself
        db.delete(db_config)
        
        # 2. Get the tools to be deleted to clean up mappings
        tools_to_delete = db.query(Tool).filter(
            Tool.user_id == user_id,
            Tool.server_url == server_url
        ).all()
        tool_ids = [t.id for t in tools_to_delete]
        
        # 3. Delete mappings for these tools
        if tool_ids:
            from app.utils.database import ToolConfigMapping
            db.query(ToolConfigMapping).filter(
                ToolConfigMapping.tool_id.in_(tool_ids)
            ).delete(synchronize_session=False)

        # 4. Delete all tools associated with this user and server URL
        deleted_tools_count = len(tools_to_delete)
        for t in tools_to_delete:
            db.delete(t)
        
        db.commit()
        logger.info(f"Deleted server config ID {server_id} for user {user_id}.")

        # --- INVALIDATE CACHE ---
        from app.utils.cache import tool_cache
        tool_cache.invalidate(user_id)
        # ------------------------

        if deleted_tools_count > 0:
            logger.info(f"Deleted {deleted_tools_count} associated tools and their mappings from {server_url} for user {user_id}.")
            
        return {"message": f"Server configuration and {deleted_tools_count} associated tools deleted successfully."}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete server config {server_id} for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


# --- (MODIFIED) Synchronize Endpoint ---

@router.post(
    "/{user_id}/synchronize",
    response_model=SyncResponse,
    summary="Synchronize Tools from All Saved Servers",
    description="Fetches all active server configurations for the user from the DB and synchronizes their tools."
)
async def synchronize_servers(
    user_id: str,
    force_refresh: bool = True,
    db: Session = Depends(get_db)
) -> SyncResponse:
    """
    Connects to each *active*, *saved* server for the given user, 
    fetches its available tools, and caches them in the `Tool` database table.

    Args:
        user_id (str): The unique identifier for the user.
        force_refresh (bool, optional): Set to true to force a refresh, deleting old tools before fetching new ones. Defaults to False.
        db (Session, optional): Database session dependency.

    Returns:
        SyncResponse: A response containing the synchronization results for each server.

    Raises:
        HTTPException: If no active servers are found or an internal server error occurs.
    """
    
    # 1. Fetch all active server configs from the DB
    db_configs = db.query(UserServerConfig).filter(
        UserServerConfig.user_id == user_id,
        UserServerConfig.is_active == True
    ).all()

    if not db_configs:
        logger.warning(f"No active server configurations found for user {user_id}. Nothing to synchronize.")
        # Return an empty success response
        return SyncResponse(results={})

    # 2. Convert them to the ServerAuth model format
    urls_with_auth = [
        ServerAuth(url=config.url, token=config.token) for config in db_configs
    ]

    if not urls_with_auth:
        logger.info(f"No active server URLs found for user {user_id} after processing.")
        return SyncResponse(results={})

    start_time = time.perf_counter()
    start_dt = datetime.datetime.utcnow()

    try:
        # 3. Pass this list to the server manager
        result_dict = await server_manager.connect_servers(
            urls_with_auth=urls_with_auth,
            user_id=user_id,
            force_refresh=force_refresh
        )

        latency_sec = time.perf_counter() - start_time
        end_dt = datetime.datetime.utcnow()

        # --- Log the sync transaction ---
        log_transaction(
            db=db,
            user_id=user_id,
            session_id="background-sync-" + str(uuid.uuid4())[:8],
            server_name="proxcp-server",
            method="system/synchronize",
            params={"server_count": len(urls_with_auth), "force_refresh": force_refresh},
            status="accepted",
            response_data=result_dict,
            latency_seconds=latency_sec,
            start_timestamp=start_dt,
            end_timestamp=end_dt
        )

        # --- INVALIDATE CACHE AFTER SYNC ---
        from app.utils.cache import tool_cache
        tool_cache.invalidate(user_id)
        # -----------------------------------

        return result_dict

    except Exception as e:
        logger.error(f"Synchronization failed for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {e}")

@router.get(
    "/{user_id}/servers/{server_id}/status",
    summary="Check Server Status",
    description="Pings the server to check if it's reachable and returns the status."
)
async def check_server_status(
    user_id: str,
    server_id: uuid.UUID,
    db: Session = Depends(get_db)
):
    import time
    
    db_config = db.query(UserServerConfig).filter(
        UserServerConfig.id == server_id,
        UserServerConfig.user_id == user_id
    ).first()

    if not db_config:
        raise HTTPException(status_code=404, detail="Server configuration not found.")
    
    if not db_config.is_active:
        return {"status": "inactive"}

    try:
        auth_object = BearerAuth(db_config.token) if db_config.token else None
        start = time.perf_counter()
        async with Client(str(db_config.url), auth=auth_object, timeout=5) as client:
            # list_tools acts as a ping
            await client.list_tools()
        latency = time.perf_counter() - start
        return {"status": "online", "latency_ms": round(latency * 1000, 2)}
    except Exception as e:
        logger.warning(f"Server {db_config.url} offline: {e}")
        return {"status": "offline", "error": str(e)}
