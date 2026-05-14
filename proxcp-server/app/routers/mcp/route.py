import uuid
import json
import logging
import time
import datetime # <-- ADDED
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Query, APIRouter, Depends, Header, status
from pydantic import BaseModel, ValidationError, ConfigDict
from sse_starlette.sse import EventSourceResponse
import asyncio
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from sqlalchemy import select # <-- ADDED
import os
from dotenv import load_dotenv # type: ignore

# Use the correct client import provided
from fastmcp import Client 
from fastmcp.client.auth import BearerAuth

# --- Import from new utility files ---
from app.utils.database import get_db, Tool, ToolConfigMapping, ApiKey
from app.utils.network import rewrite_docker_url
from app.utils.connections import connection_manager
from app.utils.toon import to_toon
# Using the path from your provided file
from app.utils.track import log_transaction
# -------------------------------------

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

router = APIRouter()

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET")
# --- (MODIFIED) ---
# Set "HS256" as the default algorithm if it's not in the .env file.
# This must match the algorithm you use to *generate* the token.
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
logger.info(f"Using JWT_ALGORITHM: {JWT_ALGORITHM}") # Added log for verification
# ------------------

# --- (MODIFIED) Authentication toggle ---
DISABLE_AUTH = False

# In-memory storage for sessions
# {session_id: {"tool_map": {tool_name: {"url": str, "token": str}}, "resource_map": {uri: {"url": str, "token": str}}, "prompt_map": {name: {"url": str, "token": str}}}}
sessions: Dict[str, Dict[str, Any]] = {}  

# JSON-RPC models
class JSONRPCBase(BaseModel):
    jsonrpc: str = "2.0"

class JSONRPCRequest(JSONRPCBase):
    model_config = ConfigDict(extra='allow')
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[int] = None

class JSONRPCNotification(JSONRPCBase):
    model_config = ConfigDict(extra='allow')
    method: str
    params: Optional[Dict[str, Any]] = None

class JSONRPCResponse(JSONRPCBase):
    id: Optional[int]
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None

# --- PROTOCOL CONSTANTS ---
PROTOCOL_RESOURCES = [
    {
        "uri": "file://protocol/rules",
        "name": "get_rules",
        "description": "PROXCP Protocol Rules",
        "mimeType": "text/markdown"
    }
]

PROTOCOL_TEMPLATES = [
    {
        "name": "get_weather",
        "uriTemplate": "weather://{city}/current",
        "description": "Provides mock weather information for a specific city.",
        "mimeType": "text/plain"
    },
    {
        "name": "get_path_content",
        "uriTemplate": "path://{filepath*}",
        "description": "Echoes back the path requested via wildcard.",
        "mimeType": "text/plain"
    },
    {
        "name": "search_resources",
        "uriTemplate": "api://search{?query,limit}",
        "description": "Simulates a searchable resource index with query parameters.",
        "mimeType": "text/plain"
    }
]

PROTOCOL_RULES_CONTENT = """# PROXCP PROTOCOL RULES

1. SYSTEM INTEGRITY
   - All connections must be via SSE or STDIO transport.
   - API Keys (pxp-*) must be kept confidential.

2. RESOURCE ACCESS
   - Dynamic resources are lazy-loaded on demand.
   - Resource templates require valid URI parameter replacement.

3. LLM INTERACTION
   - Use TOON format for optimized token consumption.
   - Prompts must be used for structured conversation initialization.

4. EMERGENCY PROTOCOLS
   - In case of sync failure, trigger full server refresh.
   - Transaction logs are the source of truth for audit trails.
"""
# ---------------------------

# Dependency to validate token and extract username and tool config id
async def get_auth_info_from_token(
    authorization: Optional[str] = Header(None), 
    token: Optional[str] = Query(None),
    toon_header: Optional[str] = Header(None, alias="Toon"),
    db: Session = Depends(get_db)
):
    if DISABLE_AUTH:
        return "user123", None, False

    # Allow token to be passed via query parameter (useful for EventSource which can't send custom headers)
    if not authorization and not token:
        logger.error("No authorization token provided")
        raise HTTPException(status_code=401, detail="No authorization token provided")

    # Determine if TOON mode is requested
    is_toon = (toon_header is not None) or \
              (authorization and "toon" in authorization.lower()) or \
              (token and "toon" in token.lower())

    # CRITICAL: Use the token exactly as provided. 
    # Do NOT strip 'Bearer ' or any other prefix. The user must provide the raw token.
    token_str = authorization if authorization else token

    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token")

    # --- API Key Lookup (pxp-...) ---
    if token_str.startswith("pxp-"):
        logger.debug(f"Verifying API key: {token_str[:10]}...")
        query = select(ApiKey).where(ApiKey.key == token_str)
        result = db.execute(query)
        api_key = result.scalar_one_or_none()

        if not api_key:
            logger.error("API key not found in registry")
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        if not api_key.is_active:
            logger.warning(f"Rejected deactivated key for config: {api_key.tool_config_id}")
            raise HTTPException(status_code=403, detail="API key is deactivated")
            
        return api_key.user_id, api_key.tool_config_id, is_toon
    # --------------------------------

    try:
        if not JWT_SECRET:
            raise HTTPException(status_code=401, detail="Missing JWT configuration")
            
        # This will now correctly use ["HS256"]
        payload = jwt.decode(token_str, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
        name = payload.get("user_id")
        tool_config_id: Optional[str] = payload.get("tool_config_id")
        
        # Also check for toon claim in JWT
        if payload.get("toon") is True:
            is_toon = True
        
        if name is None:
            logger.error("user_id not found in JWT payload")
            raise HTTPException(status_code=401, detail="Invalid token")

        # --- VALIDATION: Check if API key is active ---
        if tool_config_id:
            logger.debug(f"Validating API key status for tool_config_id: {tool_config_id}")
            query = select(ApiKey).where(ApiKey.tool_config_id == tool_config_id)
            result = db.execute(query)
            api_key = result.scalar_one_or_none()
            
            if not api_key:
                logger.error(f"API key record not found in DB for tool_config_id: {tool_config_id}")
                raise HTTPException(status_code=401, detail="API key record not found")
                
            if not api_key.is_active:
                logger.warning(f"Rejected request from deactivated API key: {tool_config_id} (User: {name})")
                raise HTTPException(status_code=403, detail="API key is deactivated")
            
            logger.debug(f"API key {tool_config_id} is active and valid.")
        # -----------------------------------------------

        logger.debug(f"Extracted user_id: {name}, tool_config_id: {tool_config_id}")
        return name, tool_config_id, is_toon
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/mcp")
async def sse_endpoint(
    authorization: Optional[str] = Header(None), 
    token: Optional[str] = Query(None),
    toon_header: Optional[str] = Header(None, alias="Toon"),
    db: Session = Depends(get_db)
):
    """Establish SSE connection. Bypasses JWT auth if DISABLE_AUTH=True."""
    if DISABLE_AUTH:
        username = "user123"
        tool_config_id = None
        is_toon = (toon_header is not None)
        logger.debug(f"Authentication disabled, using hardcoded user_id={username}")
    else:
        username, tool_config_id, is_toon = await get_auth_info_from_token(authorization, token, toon_header, db)
        logger.debug(f"Authentication enabled, user_id: {username}")

    session_id = str(uuid.uuid4()).replace('-', '')
    logger.debug(f"Created new session with ID: {session_id} for user: {username}")
    
    # Log connection initiation
    log_transaction(
        db=db,
        user_id=username,
        session_id=session_id,
        server_name="proxcp-server",
        method="sse/connect",
        params={"tool_config_id": tool_config_id},
        status="accepted",
        tool_config_id=tool_config_id # <-- ADDED
    )

    queue = asyncio.Queue()
    
    sessions[session_id] = {
        "queue": queue, 
        "username": username,
        "tool_config_id": tool_config_id,
        "tool_map": {},
        "resource_map": {},
        "prompt_map": {},
        "is_toon": is_toon
    }

    sse_start_time = time.perf_counter()
    sse_start_dt = datetime.datetime.utcnow()

    async def event_generator():
        logger.debug(f"[{session_id}] Starting SSE writer")
        endpoint_event = {
            "event": "endpoint",
            "data": f"/messages/?session_id={session_id}"
        }
        yield endpoint_event
        logger.debug(f"[{session_id}] Sent endpoint event: {endpoint_event['data']}")

        try:
            while True:
                try:
                    # Close connection after 15 minutes of inactivity
                    message = await asyncio.wait_for(queue.get(), timeout=900.0)
                except asyncio.TimeoutError:
                    logger.debug(f"[{session_id}] Connection timed out after 15 minutes of inactivity, closing")
                    break

                logger.debug(f"[{session_id}] Sending message via SSE: {message}")
                yield {
                    "event": "message",
                    "data": json.dumps(message)
                }
        except asyncio.CancelledError:
            logger.debug(f"[{session_id}] Closing SSE connection (cancelled)")
            raise
        except Exception as e:
            logger.error(f"[{session_id}] SSE error: {e}")
            raise
        finally:
            # Clean up session
            if session_id in sessions:
                del sessions[session_id]
            
            # Log connection closure
            duration = time.perf_counter() - sse_start_time
            # Use a fresh DB session for the final log because the original one might be closed
            from app.utils.database import SessionLocal
            with SessionLocal() as final_db:
                log_transaction(
                    db=final_db,
                    user_id=username,
                    session_id=session_id,
                    server_name="proxcp-server",
                    method="sse/disconnect",
                    params={"duration_seconds": duration},
                    status="accepted",
                    latency_seconds=duration,
                    start_timestamp=sse_start_dt,
                    end_timestamp=datetime.datetime.utcnow(),
                    tool_config_id=tool_config_id # <-- ADDED
                )

    logger.debug(f"[{session_id}] Starting SSE response task")
    return EventSourceResponse(event_generator(), ping=15)

@router.post("/mcp")
async def handle_mcp_post(
    body: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    auth_info: tuple = Depends(get_auth_info_from_token)
):
    """Handle standard JSON-RPC POST requests to the MCP endpoint."""
    username, tool_config_id, is_toon = auth_info
    logger.debug(f"Received POST request to /mcp from user: {username}")
    
    if body is None:
        raise HTTPException(status_code=400, detail="Request body cannot be empty")
        
    try:
        request = JSONRPCRequest(**body)
        # Use None for session_id to indicate a stateless POST request
        response = await handle_request(request, None, username, tool_config_id, db, is_toon)
        return response
    except ValidationError as e:
        logger.error(f"JSON-RPC validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC message: {e}")
    except Exception as e:
        logger.error(f"Error handling MCP POST: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Messages endpoint
@router.post("/messages/")
async def handle_messages(
    session_id: str = Query(...),
    body: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db)
):
    """Handle JSON-RPC messages. Uses session username (user123 if DISABLE_AUTH=True)."""
    logger.debug(f"[{session_id}] Handling POST message")
    logger.debug(f"[{session_id}] Received JSON: {body}")

    if session_id not in sessions:
        logger.error(f"Invalid session ID: {session_id}. Available sessions: {list(sessions.keys())}")
        raise HTTPException(status_code=404, detail="Session not found")

    # This username comes from the session, which was set in /mcp
    queue = sessions[session_id]["queue"]
    username = sessions[session_id]["username"]
    tool_config_id = sessions[session_id].get("tool_config_id")
    is_toon = sessions[session_id].get("is_toon", False)

    try:
        if body is None:
            raise ValueError("Request body cannot be empty")
        if "id" in body:
            request = JSONRPCRequest(**body)
            logger.debug(f"[{session_id}] Validated client message: root={request}")
            response = await handle_request(request, session_id, username, tool_config_id, db, is_toon)
            await queue.put(response)
        else:
            notification = JSONRPCNotification(**body)
            logger.debug(f"[{session_id}] Validated client message: root={notification}")
            await handle_notification(notification, session_id, username, tool_config_id, db)
    except ValidationError as e:
        logger.error(f"[{session_id}] JSON-RPC validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC message: {e}")
    except Exception as e:
        logger.error(f"[{session_id}] Invalid JSON-RPC message: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC message: {e}")

    return {"status": "accepted"}

# Handle JSON-RPC requests
async def handle_request(
    request: JSONRPCRequest, 
    session_id: Optional[str], 
    username: str, 
    tool_config_id: Optional[str], 
    db: Session,
    is_toon: bool = False
) -> Dict[str, Any]:
    # Note: 'username' is now the authenticated user_id from the session
    logger.debug(f"[{session_id or 'stateless'}] Processing request: {request.method} by user: {username}")
    
    start_time = time.perf_counter()
    start_dt = datetime.datetime.utcnow()
    
    # --- EXPERIMENTAL: TOON Formatting ---
    # Moved detection to session level
    # ------------------------------------

    response = JSONRPCResponse(id=request.id)

    tool_name_to_log: Optional[str] = None
    latency_sec: Optional[float] = None
    
    try:
        if request.method == "initialize":
            response.result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "experimental": {},
                    "prompts": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "tools": {"listChanged": False}
                },
                "serverInfo": {"name": "proxcp-server", "version": "1.0.0"}
            }
        elif request.method == "resources/list":
            logger.debug(f"[{session_id or 'stateless'}] Fetching resources for user: {username}")
            from app.utils.cache import tool_cache
            cached_resources = tool_cache.get_resources(username, tool_config_id)
            
            static_resources = PROTOCOL_RESOURCES.copy()
            if session_id and session_id in sessions:
                resource_map = sessions[session_id].get("resource_map", {})
                resource_map.clear()
            else:
                resource_map = None

            for r in cached_resources:
                if not r.get("is_template"):
                    static_resources.append({
                        "uri": r["uri"],
                        "name": r["name"],
                        "description": r["description"],
                        "mimeType": r["mimeType"]
                    })
                    if resource_map is not None:
                        resource_map[r["uri"]] = {"url": r["server_url"]}

            response.result = {"resources": static_resources}
            if is_toon:
                response.result["toon"] = to_toon(static_resources)

        elif request.method == "resources/templates/list":
            logger.debug(f"[{session_id or 'stateless'}] Fetching resource templates for user: {username}")
            from app.utils.cache import tool_cache
            cached_resources = tool_cache.get_resources(username, tool_config_id)
            
            templates = PROTOCOL_TEMPLATES.copy()
            if session_id and session_id in sessions:
                resource_map = sessions[session_id].get("resource_map", {})
            else:
                resource_map = None

            for r in cached_resources:
                if r.get("is_template"):
                    templates.append({
                        "uriTemplate": r["uri"],
                        "name": r["name"],
                        "description": r["description"],
                        "mimeType": r["mimeType"]
                    })
                    if resource_map is not None:
                        resource_map[r["uri"]] = {"url": r["server_url"]}

            response.result = {"resourceTemplates": templates}
            if is_toon:
                response.result["toon"] = to_toon(templates)

        elif request.method == "resources/read":
            params = request.params or {}
            uri = params.get("uri")
            if not uri:
                response.error = {"code": -32602, "message": "URI is required"}
            elif uri == "file://protocol/rules":
                response.result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/markdown",
                            "text": PROTOCOL_RULES_CONTENT
                        }
                    ]
                }
            elif uri.startswith("weather://"):
                city = uri.split("/")[-2] if uri.endswith("/current") else "Unknown"
                response.result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/plain",
                            "text": f"Mock weather for {city}: Sunny, 72°F"
                        }
                    ]
                }
            elif uri.startswith("path://"):
                path = uri.replace("path://", "")
                response.result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/plain",
                            "text": f"Echo: {path}"
                        }
                    ]
                }
            elif uri.startswith("api://search"):
                response.result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "text/plain",
                            "text": f"Search results for query at {uri}"
                        }
                    ]
                }
            else:
                target = None
                if session_id and session_id in sessions:
                    target = sessions[session_id].get("resource_map", {}).get(uri)
                
                if not target:
                    # Fallback scan DB
                    from app.utils.database import Resource, UserServerConfig
                    query = (
                        select(Resource, UserServerConfig.token)
                        .join(UserServerConfig, (Resource.server_url == UserServerConfig.url) & (Resource.user_id == UserServerConfig.user_id))
                        .where(Resource.user_id == username, Resource.uri == uri, Resource.is_active == True)
                    )
                    res_row = db.execute(query).first()
                    if res_row:
                        target = {"url": res_row[0].server_url, "token": res_row[1]}

                if not target:
                    response.error = {"code": -32601, "message": f"Resource {uri} not found"}
                else:
                    client = await connection_manager.get_client(target["url"], target.get("token"))
                    res = await client.read_resource(uri)
                    
                    if isinstance(res, list):
                        response.result = {"contents": res}
                    elif hasattr(res, "model_dump"):
                        response.result = res.model_dump()
                    else:
                        response.result = res
            
            # Apply TOON if requested (works for both built-ins and dynamic resources)
            if is_toon and response.result and "contents" in response.result:
                response.result["toon"] = to_toon(response.result["contents"])

        elif request.method == "prompts/list":
            logger.debug(f"[{session_id or 'stateless'}] Fetching prompts for user: {username}")
            from app.utils.cache import tool_cache
            cached_prompts = tool_cache.get_prompts(username, tool_config_id)
            
            prompts_list = []
            if session_id and session_id in sessions:
                prompt_map = sessions[session_id].get("prompt_map", {})
                prompt_map.clear()
            else:
                prompt_map = None

            for p in cached_prompts:
                prompts_list.append({
                    "name": p["name"],
                    "description": p["description"],
                    "arguments": p["arguments"]
                })
                if prompt_map is not None:
                    prompt_map[p["name"]] = {"url": p["server_url"]}
            
            response.result = {"prompts": prompts_list}
            if is_toon:
                response.result["toon"] = to_toon(prompts_list)

        elif request.method == "prompts/get":
            params = request.params or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if not name:
                response.error = {"code": -32602, "message": "Prompt name is required"}
            else:
                target = None
                if session_id and session_id in sessions:
                    target = sessions[session_id].get("prompt_map", {}).get(name)
                
                if not target:
                    # Fallback scan DB
                    from app.utils.database import Prompt, UserServerConfig
                    query = (
                        select(Prompt, UserServerConfig.token)
                        .join(UserServerConfig, (Prompt.server_url == UserServerConfig.url) & (Prompt.user_id == UserServerConfig.user_id))
                        .where(Prompt.user_id == username, Prompt.name == name, Prompt.is_active == True)
                    )
                    p_row = db.execute(query).first()
                    if p_row:
                        target = {"url": p_row[0].server_url, "token": p_row[1]}

                if not target:
                    response.error = {"code": -32601, "message": f"Prompt {name} not found"}
                else:
                    client = await connection_manager.get_client(target["url"], target.get("token"))
                    res = await client.get_prompt(name, args)
                    
                    if hasattr(res, "model_dump"):
                        response.result = res.model_dump()
                    else:
                        response.result = res
                        
                    if is_toon and response.result:
                        response.result["toon"] = to_toon(response.result)
        
        elif request.method == "tools/list":
            logger.debug(f"[{session_id or 'stateless'}] Fetching tools for user: {username}, config: {tool_config_id}")
            
            from app.utils.cache import tool_cache
            
            # Serve from memory cache (refreshes from DB every 5 minutes)
            # This avoids expensive auto-syncs and frequent DB reads.
            cached_tools = tool_cache.get_tools(username, tool_config_id)
            
            tools_list = []
            
            if session_id and session_id in sessions:
                session_tool_map = sessions[session_id].get("tool_map")
                if session_tool_map is None:
                     logger.warning(f"[{session_id}] tool_map not found. Re-initializing.")
                     sessions[session_id]["tool_map"] = {}
                     session_tool_map = sessions[session_id]["tool_map"]
                
                session_tool_map.clear()
            else:
                session_tool_map = None
            
            for tool_data in cached_tools:
                try:
                    tool_schema = json.loads(tool_data["definition"]) if tool_data.get("definition") else {}
                    tool_name = tool_data["name"]
                    server_url = tool_data["server_url"]
                    
                    formatted_tool = {
                        "name": tool_name,
                        "title": tool_name,
                        "description": tool_schema.get("description", ""),
                        "inputSchema": tool_schema.get("inputSchema", {})
                    }
                    tools_list.append(formatted_tool)
                    
                    if session_tool_map is not None:
                        session_tool_map[tool_name] = {
                            "url": server_url,
                            "token": tool_data.get("server_token")
                        }
                            
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Skipping invalid tool definition for user {username}, tool {tool_data.get('name')}: {e}")
            
            response.result = {"tools": tools_list}
            if is_toon:
                response.result["toon"] = to_toon(tools_list)
            logger.debug(f"[{session_id or 'stateless'}] Returning {len(tools_list)} tools for user {username}")

        elif request.method == "tools/call":
            target_server_url = "" # For logging
            try:
                params = request.params or {}
                tool_name = params.get("name")
                tool_name_to_log = tool_name
                arguments = params.get("arguments") or {}

                # Check for extraArgs in params or as a top-level field in the request
                extra_args = params.get("extraArgs")
                if not extra_args and request.model_extra:
                    extra_args = request.model_extra.get("extraArgs")

                if not tool_name:
                    response.error = {"code": -32602, "message": "Invalid params: 'name' is required."}
                else:
                    # Look up the tool in the database to ensure it is still active and synced
                    if tool_config_id:
                        tool_db = db.query(Tool).join(
                            ToolConfigMapping, Tool.id == ToolConfigMapping.tool_id
                        ).filter(
                            Tool.user_id == username,
                            Tool.name == tool_name,
                            Tool.is_active == True,
                            ToolConfigMapping.tool_config_id == tool_config_id
                        ).first()
                    else:
                        tool_db = db.query(Tool).filter(
                            Tool.user_id == username,
                            Tool.name == tool_name,
                            Tool.is_active == True
                        ).first()

                    if not tool_db:
                        logger.error(f"[{session_id or 'stateless'}] Tool '{tool_name}' not found or inactive in DB for user {username}.")
                        response.error = {"code": -32601, "message": f"Tool '{tool_name}' is not currently served or has been removed."}
                    else:
                        # --- SMART EXTRA ARGS INJECTION ---
                        # Only pass extraArgs (like API_auth) if the tool actually expects them in its schema.
                        # This prevents "unexpected argument" errors on tools with strict validation.
                        if extra_args and isinstance(extra_args, dict):
                            try:
                                tool_schema = json.loads(tool_db.definition) if tool_db.definition else {}
                                # FastMCP usually nests properties under inputSchema
                                properties = tool_schema.get("inputSchema", {}).get("properties", {})
                                if not properties and "parameters" in tool_schema: # Standard JSON-RPC schema
                                    properties = tool_schema.get("parameters", {}).get("properties", {})
                                
                                for k, v in extra_args.items():
                                    if k in properties:
                                        clean_v = v.strip() if isinstance(v, str) else v
                                        arguments[k] = clean_v
                                        logger.debug(f"[{session_id or 'stateless'}] Smart-injected extraArg '{k}' into tool '{tool_name}'")
                            except Exception as e:
                                logger.warning(f"[{session_id or 'stateless'}] Smart injection failed for '{tool_name}': {e}")
                        # ----------------------------------

                        target_server_url = rewrite_docker_url(tool_db.server_url)

                        token = tool_db.server_token
                        
                        # Better Logging for Tool Call
                        masked_token = f"{token[:10]}...{token[-10:]}" if token and len(token) > 20 else ("[PROVIDED]" if token else "[NONE]")
                        logger.info(f"[{session_id or 'stateless'}] --- MCP Tool Execution ---")
                        logger.info(f"[{session_id or 'stateless'}] Tool: {tool_name}")
                        logger.info(f"[{session_id or 'stateless'}] Target URL: {target_server_url}")
                        logger.info(f"[{session_id or 'stateless'}] Auth Token: {masked_token}")
                        logger.info(f"[{session_id or 'stateless'}] ------------------------")
                        
                        start_time_internal = time.perf_counter()
                        try:
                            client = await connection_manager.get_client(target_server_url, token)
                            logger.debug(f"[{session_id or 'stateless'}] Calling tool '{tool_name}' via persistent connection")
                            result_data = await client.call_tool(tool_name, arguments) 
                            # We still track internal latency for logging, but total latency is also tracked
                            logger.debug(f"[{session_id}] Tool '{tool_name}' internal execution time: {time.perf_counter() - start_time_internal:.4f}s.")
                            
                            # --- NESTED ERROR DETECTION ---
                            if hasattr(result_data, 'content') and len(result_data.content) > 0:
                                for item in result_data.content:
                                    if item.type == 'text':
                                        try:
                                            parsed = json.loads(item.text)
                                            if isinstance(parsed, dict) and "error" in parsed:
                                                result_data.is_error = True
                                                logger.warning(f"[{session_id}] Detected error in tool output: {parsed['error']}")
                                        except: pass
                            # ------------------------------
                            
                            response.result = result_data
                            # Calculate latency here for logging
                            current_latency = time.perf_counter() - start_time
                            logger.debug(f"[{session_id}] Tool '{tool_name}' call successful. Latency: {current_latency:.4f}s.")
                        except Exception as e:
                            # If persistent connection failed, we might need to clear it from manager
                            logger.error(f"[{session_id}] Persistent connection error for {target_server_url}: {e}")
                            # You might want logic here to remove the dead client from connection_manager
                            raise

            except asyncio.CancelledError:
                # Silence the expected CancelledError from fastmcp session runner
                logger.debug(f"[{session_id}] FastMCP session runner task cancelled (expected).")
            except Exception as e:
                logger.error(f"[{session_id}] FastMCP Tool call for '{tool_name_to_log}' failed: {e}")
                response.error = {"code": -32000, "message": f"Tool execution error: {str(e)}"}

        elif request.method == "ping":
            response.result = {}
        elif request.method == "prompts/list":
            response.result = {"prompts": []}
        elif request.method == "resources/templates/list":
            response.result = {"resourceTemplates": []}
        else:
            response.error = {"code": -32601, "message": "Method not found"}

        # --- EXPERIMENTAL: Apply TOON transformation ---
        if is_toon and response.result:
            from app.utils.toon import to_toon
            try:
                # 1. Handle tools/list specifically
                if request.method == "tools/list" and "tools" in response.result:
                    # Simplify tool list for TOON
                    simplified_tools = []
                    for t in response.result["tools"]:
                        simplified_tools.append({
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "schema": t.get("inputSchema", {})
                        })
                    response.result = {"tools_toon": to_toon(simplified_tools)}

                # 2. Handle ToolResult (from tools/call)
                elif hasattr(response.result, 'content'):
                    for item in response.result.content:
                        if item.type == 'text':
                            try:
                                # Try to parse text as JSON and convert to TOON
                                data = json.loads(item.text)
                                item.text = to_toon(data)
                            except:
                                pass # Not JSON
            except Exception as e:
                logger.warning(f"TOON transformation failed: {e}")
        # -----------------------------------------------
            
    except Exception as e:
        logger.error(f"[{session_id}] Unhandled error processing request {request.method}: {e}", exc_info=True)
        if not response.error:
            response.error = {"code": -32000, "message": f"Internal server error: {str(e)}"}
    finally:
        latency_sec = time.perf_counter() - start_time
        end_dt = datetime.datetime.utcnow()

    # --- Single Logging Point ---
    
    final_response_dict = response.model_dump(exclude_none=True)

    log_status: str
    log_response_data: Optional[Dict[str, Any]]

    if "error" in final_response_dict:
        log_status = "error"
        log_response_data = final_response_dict.get("error")
    else:
        log_status = "accepted"
        log_response_data = final_response_dict.get("result")
    
    log_transaction(
        db=db,
        user_id=username,
        session_id=session_id or "stateless",
        server_name="proxcp-server",
        method=request.method,
        params=request.params,
        status=log_status,
        response_data=log_response_data,
        tool_name=tool_name_to_log,
        latency_seconds=latency_sec,
        start_timestamp=start_dt,
        end_timestamp=end_dt,
        tool_config_id=tool_config_id # <-- ADDED
    )

    logger.debug(f"[{session_id}] Response sent: {final_response_dict}")
    return final_response_dict
    # --- End Logging ---

# Handle JSON-RPC notifications (Unchanged)
async def handle_notification(notification: JSONRPCNotification, session_id: Optional[str], username: str, tool_config_id: Optional[str], db: Session):
    logger.debug(f"[{session_id or 'stateless'}] Received notification: {notification.method} by user: {username}")
    
    start_time = time.perf_counter()
    start_dt = datetime.datetime.utcnow()

    params = notification.params or {}
    if notification.model_extra and "extraArgs" in notification.model_extra:
        params["extraArgs"] = notification.model_extra["extraArgs"]

    # Process notification
    if notification.method == "notifications/initialized":
        logger.debug(f"[{session_id or 'stateless'}] Processed initialized notification")
    else:
        logger.warning(f"[{session_id or 'stateless'}] Unknown notification method: {notification.method}")

    latency_sec = time.perf_counter() - start_time
    end_dt = datetime.datetime.utcnow()

    log_transaction(
        db=db,
        user_id=username,
        session_id=session_id or "stateless",
        server_name="proxcp-server",
        method=notification.method,
        params=params,
        status="accepted",
        response_data=None,
        tool_name=None,
        latency_seconds=latency_sec,
        start_timestamp=start_dt,
        end_timestamp=end_dt,
        tool_config_id=tool_config_id # <-- ADDED
    )
