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
import os
from dotenv import load_dotenv # type: ignore

# Use the correct client import provided
from fastmcp import Client 
from fastmcp.client.auth import BearerAuth

# --- Import from new utility files ---
from app.utils.database import get_db, Tool, ToolConfigMapping
from app.utils.network import rewrite_docker_url
from app.utils.connections import connection_manager
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
# {session_id: {"tool_map": {tool_name: {"url": str, "token": str}}}}
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

# Dependency to validate token and extract username and tool config id
async def get_auth_info_from_token(authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    if DISABLE_AUTH:
        return "user123", None

    # Allow token to be passed via query parameter (useful for EventSource which can't send custom headers)
    if not authorization and not token:
        logger.error("No authorization token provided")
        raise HTTPException(status_code=401, detail="No authorization token provided")

    # CRITICAL: Use the token exactly as provided. 
    # Do NOT strip 'Bearer ' or any other prefix. The user must provide the raw token.
    token_str = authorization if authorization else token

    try:
        if not token_str or not JWT_SECRET:
            raise HTTPException(status_code=401, detail="Missing token or configuration")
            
        # This will now correctly use ["HS256"]
        payload = jwt.decode(token_str, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
        name = payload.get("user_id")
        tool_config_id: Optional[str] = payload.get("tool_config_id")
        if name is None:
            logger.error("user_id not found in JWT payload")
            raise HTTPException(status_code=401, detail="Invalid token")
        logger.debug(f"Extracted user_id: {name}, tool_config_id: {tool_config_id}")
        return name, tool_config_id
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

@router.get("/mcp")
async def sse_endpoint(
    authorization: Optional[str] = Header(None), 
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Establish SSE connection. Bypasses JWT auth if DISABLE_AUTH=True."""
    if DISABLE_AUTH:
        username = "user123"
        tool_config_id = None
        logger.debug(f"Authentication disabled, using hardcoded user_id={username}")
    else:
        username, tool_config_id = await get_auth_info_from_token(authorization, token)
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
        status="accepted"
    )

    queue = asyncio.Queue()
    
    sessions[session_id] = {
        "queue": queue, 
        "username": username,
        "tool_config_id": tool_config_id,
        "tool_map": {}
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
                    end_timestamp=datetime.datetime.utcnow()
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
    username, tool_config_id = auth_info
    logger.debug(f"Received POST request to /mcp from user: {username}")
    
    if body is None:
        raise HTTPException(status_code=400, detail="Request body cannot be empty")
        
    try:
        request = JSONRPCRequest(**body)
        # Use None for session_id to indicate a stateless POST request
        response = await handle_request(request, None, username, tool_config_id, db)
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

    try:
        if body is None:
            raise ValueError("Request body cannot be empty")
        if "id" in body:
            request = JSONRPCRequest(**body)
            logger.debug(f"[{session_id}] Validated client message: root={request}")
            response = await handle_request(request, session_id, username, tool_config_id, db)
            await queue.put(response)
        else:
            notification = JSONRPCNotification(**body)
            logger.debug(f"[{session_id}] Validated client message: root={notification}")
            await handle_notification(notification, session_id, username, db)
    except ValidationError as e:
        logger.error(f"[{session_id}] JSON-RPC validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC message: {e}")
    except Exception as e:
        logger.error(f"[{session_id}] Invalid JSON-RPC message: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON-RPC message: {e}")

    return {"status": "accepted"}

# Handle JSON-RPC requests
async def handle_request(request: JSONRPCRequest, session_id: Optional[str], username: str, tool_config_id: Optional[str], db: Session) -> Dict[str, Any]:
    # Note: 'username' is now the authenticated user_id from the session
    logger.debug(f"[{session_id or 'stateless'}] Processing request: {request.method} by user: {username}")
    
    start_time = time.perf_counter()
    start_dt = datetime.datetime.utcnow()
    
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
            response.result = {"resources": []}
        
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
        end_timestamp=end_dt
    )

    logger.debug(f"[{session_id}] Response sent: {final_response_dict}")
    return final_response_dict
    # --- End Logging ---

# Handle JSON-RPC notifications (Unchanged)
async def handle_notification(notification: JSONRPCNotification, session_id: Optional[str], username: str, db: Session):
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
        end_timestamp=end_dt
    )
