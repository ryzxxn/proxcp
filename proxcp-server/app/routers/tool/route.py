from fastapi import APIRouter, Depends, Query, HTTPException, Header, Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict
import logging
import time
import datetime
import json

# --- New Imports for fastmcp ---
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
import fastmcp.exceptions as mcp_exc
# --- End New Imports ---

# --- Updated Imports ---
from app.utils.database import get_db, Tool, UserServerConfig
from app.utils.track import log_transaction
import anyio
# --- End Updated Imports ---
import uuid  # <-- ADDED


logger = logging.getLogger(__name__)

# --- Create the router ---
router = APIRouter()


# --- Pydantic Response Model ---

class ToolResponse(BaseModel):
    """
    Pydantic model for safely returning tool data to the client.
    """
    id: uuid.UUID
    user_id: str
    name: str
    custom_name: Optional[str] = None # <-- ADDED
    custom_description: Optional[str] = None # <-- ADDED
    definition: Optional[Any] # <-- CHANGED from str to Any
    server_url: str
    is_active: bool
    server_name: Optional[str]

    model_config = ConfigDict(from_attributes=True)

class ToolUpdate(BaseModel):
    custom_name: Optional[str] = None
    custom_description: Optional[str] = None

# --- Pydantic Request Model for Execution (Updated) ---

class ToolExecutionRequest(BaseModel):
    """
    Pydantic model for receiving a tool execution request from the client.
    """
    user_id: str = Field(..., description="The user's ID.")
    session_id: str = Field(..., description="The user's session ID.")
    tool_name: str = Field(..., description="The name of the tool to execute, e.g., 'add'.")
    server_url: Optional[str] = Field(None, description="The server URL of the tool to execute. Optional.")
    params: Dict[str, Any] = Field(..., description="The parameters object for the tool.")


# --- API Endpoint (Existing) ---

@router.get("/tools")
def list_user_tools(
    user_id: str = Query(..., description="The ID of the user to fetch tools for"),
    format: Optional[str] = Query(None, description="Response format: 'json' or 'toon'"),
    toon: Optional[str] = Header(None, alias="Toon"),
    db: Session = Depends(get_db)
):
    """
    Fetches a list of all tools associated with a specific user.
    Served from memory cache with 5-minute DB refresh.
    """
    from app.utils.cache import tool_cache
    from app.utils.toon import to_toon
    from fastapi.responses import Response
    
    try:
        results = tool_cache.get_tools(user_id)

        def _parse_definition(d):
            if not d: return None
            if isinstance(d, dict): return d
            try:
                return json.loads(d)
            except:
                return d

        tools = [
            ToolResponse(
                id=tool["id"],
                user_id=tool["user_id"],
                name=tool["name"],
                custom_name=tool.get("custom_name"),
                custom_description=tool.get("custom_description"),
                definition=_parse_definition(tool.get("definition")),
                server_url=tool["server_url"],
                is_active=tool["is_active"],
                server_name=tool["server_name"]
            )
            for tool in results
        ]

        if format == "toon":
            # Convert to dict for toon encoder
            tool_dicts = [t.model_dump() for t in tools]
            toon_output = to_toon(tool_dicts)
            return Response(content=toon_output, media_type="text/plain")
        
        if toon:
            # Return both JSON and TOON format for compatibility
            tool_dicts = [t.model_dump() for t in tools]
            return {
                "tools": tools,
                "toon": to_toon(tool_dicts)
            }

        return {"tools": tools}

    except Exception as e:
        logger.error(f"Error fetching tools for user_id {user_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="An error occurred while fetching tools."
        )

@router.get("/resources")
async def list_user_resources(
    user_id: str = Query(..., description="The ID of the user to fetch resources for"),
    toon: Optional[str] = Header(None, alias="Toon"),
    db: Session = Depends(get_db)
):
    """
    Fetches a list of all resources across all user's connected servers from memory cache.
    """
    from app.utils.cache import tool_cache
    from app.utils.toon import to_toon
    
    try:
        results = tool_cache.get_resources(user_id)
        
        if toon:
            return {
                "resources": results,
                "toon": to_toon(results)
            }
        return {"resources": results}
    except Exception as e:
        logger.error(f"Error fetching resources for user_id {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/prompts")
async def list_user_prompts(
    user_id: str = Query(..., description="The ID of the user to fetch prompts for"),
    toon: Optional[str] = Header(None, alias="Toon"),
    db: Session = Depends(get_db)
):
    """
    Fetches a list of all prompts across all user's connected servers from memory cache.
    """
    from app.utils.cache import tool_cache
    from app.utils.toon import to_toon
    
    try:
        results = tool_cache.get_prompts(user_id)
        
        if toon:
            return {
                "prompts": results,
                "toon": to_toon(results)
            }
        return {"prompts": results}
    except Exception as e:
        logger.error(f"Error fetching prompts for user_id {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/resources/read")
async def read_user_resource(
    user_id: str = Query(...),
    uri: str = Query(...),
    server_url: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    Reads a specific resource from a connected MCP server.
    """
    from app.utils.database import UserServerConfig
    from app.utils.connections import connection_manager
    from app.utils.toon import to_toon
    
    query = select(UserServerConfig).where(
        UserServerConfig.user_id == user_id, 
        UserServerConfig.url == server_url
    )
    server = db.execute(query).scalar_one_or_none()
    
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
        
    try:
        try:
            client = await connection_manager.get_client(server.url, server.token)
            res = await client.read_resource(uri)
        except (anyio.ClosedResourceError, Exception) as e:
            if isinstance(e, anyio.ClosedResourceError):
                logger.warning(f"Connection to {server.url} was closed, retrying once...")
                await connection_manager.remove_client(server.url, server.token)
                client = await connection_manager.get_client(server.url, server.token)
                res = await client.read_resource(uri)
            else:
                raise e
        return res.model_dump() if hasattr(res, "model_dump") else res
    except Exception as e:
        logger.error(f"Error reading resource {uri} from {server_url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prompts/get")
async def get_user_prompt(
    user_id: str = Query(...),
    name: str = Query(...),
    server_url: str = Query(...),
    arguments: Dict[str, Any] = Body({}),
    db: Session = Depends(get_db)
):
    """
    Renders a specific prompt from a connected MCP server.
    """
    from app.utils.database import UserServerConfig
    from app.utils.connections import connection_manager
    
    query = select(UserServerConfig).where(
        UserServerConfig.user_id == user_id, 
        UserServerConfig.url == server_url
    )
    server = db.execute(query).scalar_one_or_none()
    
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
        
    try:
        try:
            client = await connection_manager.get_client(server.url, server.token)
            res = await client.get_prompt(name, arguments)
        except (anyio.ClosedResourceError, Exception) as e:
            if isinstance(e, anyio.ClosedResourceError):
                logger.warning(f"Connection to {server.url} was closed, retrying once...")
                await connection_manager.remove_client(server.url, server.token)
                client = await connection_manager.get_client(server.url, server.token)
                res = await client.get_prompt(name, arguments)
            else:
                raise e
        return res.model_dump() if hasattr(res, "model_dump") else res
    except Exception as e:
        logger.error(f"Error getting prompt {name} from {server_url}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/tools/{tool_id}", response_model=ToolResponse)
def update_tool(
    tool_id: uuid.UUID,
    request: ToolUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates a tool's custom name and description.
    """
    query = select(Tool).where(Tool.id == tool_id)
    tool = db.execute(query).scalar_one_or_none()
    
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    
    if request.custom_name is not None:
        tool.custom_name = request.custom_name
    if request.custom_description is not None:
        tool.custom_description = request.custom_description
        
    db.commit()
    db.refresh(tool)
    
    # Invalidate cache
    from app.utils.cache import tool_cache
    tool_cache.invalidate(tool.user_id)
    
    return tool

# --- API Endpoint (Updated with Latency Tracking and Return) ---

@router.post("/execute", response_model=Dict[str, Any])
async def execute_user_tool(
    request: ToolExecutionRequest,
    db: Session = Depends(get_db)
):
    """
    Executes a specific tool for a user using the fastmcp client.
    
    This endpoint acts as a secure proxy:
    1. It finds the tool (and its server_url) from the DB.
    2. It finds the associated server token from the UserServerConfig table.
    3. It forwards the request to the tool's server with the correct auth.
    4. It returns the server's response (and latency) directly to the client.
    
    All successful and failed executions are logged to the Transaction table.
    """
    
    server_name_to_log = request.server_url 

    # --- ADDED: Initialize latency tracking vars ---
    latency_sec: Optional[float] = None
    start_time = time.perf_counter()
    start_dt = datetime.datetime.utcnow()
    # --- END ADDITION ---

    params_to_log = {
        "name": request.tool_name,
        "arguments": request.params
    }
    
    try:
        # 1. Find the tool
        tool = None
        if request.server_url:
            stmt = (
                select(Tool)
                .where(
                    Tool.user_id == request.user_id,
                    Tool.name == request.tool_name,
                    Tool.server_url == request.server_url,
                    Tool.is_active == True
                )
            )
            tool = db.execute(stmt).scalar_one_or_none()

        if not tool:
            # Fallback or Direct Lookup: Try to find the tool by name only for this user
            logger.info(f"Finding tool by name fallback for '{request.tool_name}' for user '{request.user_id}'.")
            fallback_stmt = (
                select(Tool)
                .where(
                    Tool.user_id == request.user_id,
                    Tool.name == request.tool_name,
                    Tool.is_active == True
                )
                .order_by(Tool.server_url)
            )
            fallback_results = db.execute(fallback_stmt).scalars().all()
            if fallback_results:
                tool = fallback_results[0]
                logger.info(f"Tool found. Using server: {tool.server_url}")

        if not tool:
            err_detail = f"Tool '{request.tool_name}'"
            if request.server_url: err_detail += f" from server '{request.server_url}'"
            err_detail += " not found or is not active."
            
            logger.warning(f"Execution attempt failed: {err_detail} User: {request.user_id}")
            raise HTTPException(status_code=404, detail=err_detail)

        # 2. Find the server token and name
        config_stmt = (
            select(UserServerConfig)
            .where(
                UserServerConfig.user_id == request.user_id,
                UserServerConfig.url == tool.server_url,
                UserServerConfig.is_active == True
            )
        )
        server_config = db.execute(config_stmt).scalar_one_or_none()

        if server_config and server_config.name:
            server_name_to_log = server_config.name

        # 3. Determine auth token
        token_to_use = None
        if server_config and server_config.token:
            token_to_use = server_config.token
            logger.debug(f"Using token from UserServerConfig for server: {tool.server_url}")
        elif tool.server_token:
            token_to_use = tool.server_token
            logger.debug(f"Using fallback token from Tool entry for server: {tool.server_url}")
        else:
            logger.debug(f"No token found for server: {tool.server_url}")
        
        auth_obj = BearerAuth(token=token_to_use) if token_to_use else None
        
        # 4. Make the outbound request
        logger.info(f"Executing tool '{tool.name}' at URL '{tool.server_url}' for user '{request.user_id}'.")
        
        try:
            from app.utils.connections import connection_manager
            client = await connection_manager.get_client(tool.server_url, token_to_use)
            logger.debug(f"Calling tool '{tool.name}' via persistent connection")
            
            call_result = await client.call_tool(tool.name, request.params) 
            
            latency_sec = time.perf_counter() - start_time
            end_dt = datetime.datetime.utcnow()
            
            logger.debug(f"Tool '{tool.name}' call successful. Latency: {latency_sec:.4f}s.")

            serializable_result = call_result.structured_content if hasattr(call_result, 'structured_content') else call_result

            # 5. Reconstruct the full JSON-RPC response
            response_payload = {
                "jsonrpc": "2.0",
                "result": serializable_result,
                "id": 1,
                "latency_seconds": latency_sec
            }
            
            # --- Log successful transaction ---
            log_transaction(
                db=db,
                user_id=request.user_id,
                session_id=request.session_id,
                server_name=server_name_to_log or tool.server_url,
                method="tools/call",
                params=params_to_log,
                status="accepted",
                response_data=response_payload,
                tool_name=request.tool_name,
                latency_seconds=latency_sec,
                start_timestamp=start_dt,
                end_timestamp=end_dt
            )
            
            return response_payload

        except Exception as e:
            latency_sec = time.perf_counter() - start_time
            end_dt = datetime.datetime.utcnow()
            
            logger.error(f"Tool execution failed for '{request.tool_name}': {e}")
            
            # Log Failure
            log_transaction(
                db=db,
                user_id=request.user_id,
                session_id=request.session_id,
                server_name=server_name_to_log or (tool.server_url if tool else "unknown"),
                method="tools/call",
                params=params_to_log,
                status="error",
                response_data={"error": str(e)},
                tool_name=request.tool_name,
                latency_seconds=latency_sec,
                start_timestamp=start_dt,
                end_timestamp=end_dt
            )
            raise HTTPException(status_code=500, detail=f"Tool execution failed: {str(e)}")

    except HTTPException as http_exc:
        # Log known HTTP errors (e.g., 404)
        log_transaction(
            db=db,
            user_id=request.user_id,
            session_id=request.session_id,
            server_name=server_name_to_log or "unknown",
            method="tools/call",
            params=params_to_log,
            status="error",
            response_data={"error": http_exc.detail, "code": http_exc.status_code},
            tool_name=request.tool_name,
            latency_seconds=latency_sec,
            start_timestamp=start_dt,
            end_timestamp=datetime.datetime.utcnow()
        )
        raise http_exc

    except mcp_exc.ToolCallError as e:
        if start_time: latency_sec = time.perf_counter() - start_time

        logger.error(f"Remote tool error for tool '{request.tool_name}': {e.message} (Code: {e.code})")
        
        error_payload = {
            "jsonrpc": "2.0",
            "error": {"code": e.code, "message": e.message, "data": e.data},
            "id": 1,
            "latency_seconds": latency_sec  # <-- ADDED
        }
        
        log_transaction(
            db=db,
            user_id=request.user_id,
            session_id=request.session_id,
            server_name=server_name_to_log or "unknown",
            method="tools/call",
            params=params_to_log,
            status="error",
            response_data=error_payload,
            tool_name=request.tool_name,
            latency_seconds=latency_sec,
            start_timestamp=start_dt,
            end_timestamp=datetime.datetime.utcnow()
        )

        raise HTTPException(status_code=500, detail=error_payload)
        
    except mcp_exc.ClientConnectionError as e:
        if start_time: latency_sec = time.perf_counter() - start_time

        logger.error(f"Network error executing tool '{request.tool_name}': {e}")
        error_detail = f"Error connecting to tool server: {e}"

        # --- UPDATED: Return consistent JSON-RPC error ---
        error_payload = {
            "jsonrpc": "2.0",
            "error": {"code": -32002, "message": error_detail},
            "id": 1,
            "latency_seconds": latency_sec
        }
        # --- END UPDATE ---

        log_transaction(
            db=db,
            user_id=request.user_id,
            session_id=request.session_id,
            server_name=server_name_to_log,
            method="tools/call",
            params=params_to_log,
            status="error",
            response_data=error_payload, # <-- Log consistent payload
            tool_name=request.tool_name,
            latency_seconds=latency_sec
        )

        raise HTTPException(
            status_code=502, # Bad Gateway
            detail=error_payload # <-- Return payload
        )
    
    except mcp_exc.FastmcpError as e:
        if start_time: latency_sec = time.perf_counter() - start_time

        logger.error(f"Fastmcp library error for tool '{request.tool_name}': {e}")
        error_detail = f"Fastmcp error: {e}"
        
        # --- UPDATED: Return consistent JSON-RPC error ---
        error_payload = {
            "jsonrpc": "2.0",
            "error": {"code": -32003, "message": str(error_detail)},
            "id": 1,
            "latency_seconds": latency_sec
        }
        # --- END UPDATE ---
        
        log_transaction(
            db=db,
            user_id=request.user_id,
            session_id=request.session_id,
            server_name=server_name_to_log,
            method="tools/call",
            params=params_to_log,
            status="error",
            response_data=error_payload, # <-- Log consistent payload
            tool_name=request.tool_name,
            latency_seconds=latency_sec
        )

        raise HTTPException(status_code=500, detail=error_payload) # <-- Return payload
        
    except Exception as e:
        if start_time: latency_sec = time.perf_counter() - start_time

        logger.error(f"Unexpected error executing tool '{request.tool_name}': {e}")
        error_detail = "An internal server error occurred."

        # --- UPDATED: Return consistent JSON-RPC error ---
        error_payload = {
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": error_detail, "data": str(e)},
            "id": 1,
            "latency_seconds": latency_sec
        }
        # --- END UPDATE ---

        log_transaction(
            db=db,
            user_id=request.user_id,
            session_id=request.session_id,
            server_name=server_name_to_log,
            method="tools/call",
            params=params_to_log,
            status="error",
            response_data=error_payload, # <-- Log consistent payload
            tool_name=request.tool_name,
            latency_seconds=latency_sec
        )

        raise HTTPException(
            status_code=500, 
            detail=error_payload # <-- Return payload
        )