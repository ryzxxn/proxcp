import json
import logging
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from collections import defaultdict
import datetime
import uuid

# --- Import from utility files ---
from app.utils.database import get_db, Transaction, Tool  # <-- ADDED Tool
# --- End Imports ---

logger = logging.getLogger(__name__)

# --- Create the router ---
router = APIRouter()


# --- Pydantic Response Models ---

class TransactionResponse(BaseModel):
    """
    Pydantic model for safely returning transaction data to the client.
    """
    id: uuid.UUID
    user_id: str
    session_id: str
    server_name: str
    jsonrpc_method: str
    
    # These will be parsed from the JSON strings in the DB
    request_params: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None
    
    status: str
    tool_name: Optional[str] = None
    tool_config_id: Optional[str] = None # <-- ADDED
    timestamp: datetime.datetime
    
    # --- UPDATED: New time tracking fields ---
    start_timestamp: Optional[datetime.datetime] = None
    end_timestamp: Optional[datetime.datetime] = None
    latency_seconds: Optional[float] = None
    # --- END UPDATE ---

    # This model does not use orm_mode=True because we are manually
    # parsing the JSON string fields (request_params, response_data)
    # for a cleaner API response.

# --- NEW: Pydantic Response Model for Prod Endpoint ---
class SessionTransactionGroup(BaseModel):
    """
    Pydantic model for returning a list of transactions 
    plus the start time of that session.
    """
    session_start_time: datetime.datetime
    transactions: List[TransactionResponse]

class ToolUsageCount(BaseModel):
    """
    Pydantic model for returning tool usage statistics.
    """
    tool_name: str
    count: int


# --- Helper Function (Groups by Session ID, Full Response) ---

def _group_transactions_by_session(results: List[Transaction]) -> Dict[str, SessionTransactionGroup]:
    """
    Helper function to parse, validate, and group a list of
    Transaction objects into a dictionary keyed by session_id.
    
    The query providing 'results' MUST be sorted by timestamp descending.
    """
    grouped_transactions = defaultdict(list)
    session_start_times = {} # To store the earliest timestamp
    
    for tx in results:
        # Manually parse JSON strings from DB into dictionaries
        try:
            params_dict = json.loads(tx.request_params) if tx.request_params else None
        except json.JSONDecodeError:
            logger.warning(f"Could not parse request_params JSON for tx_id {tx.id}")
            params_dict = {"error": "invalid_json"}

        try:
            response_dict = json.loads(tx.response_data) if tx.response_data else None
        except json.JSONDecodeError:
            logger.warning(f"Could not parse response_data JSON for tx_id {tx.id}")
            response_dict = {"error": "invalid_json"}

        # Calculate latency
        latency = None
        st = getattr(tx, 'start_timestamp', None)
        et = getattr(tx, 'end_timestamp', None)
        if st and et:
            latency = (et - st).total_seconds()

        # Create the Pydantic response object
        tx_response = TransactionResponse(
            id=tx.id,
            user_id=tx.user_id,
            session_id=tx.session_id,
            server_name=tx.server_name,
            jsonrpc_method=tx.jsonrpc_method,
            request_params=params_dict,
            status=tx.status,
            response_data=response_dict,
            tool_name=tx.tool_name,
            tool_config_id=tx.tool_config_id,
            timestamp=tx.timestamp,
            start_timestamp=st,
            end_timestamp=et,
            latency_seconds=latency
        )
        
        # Add the formatted transaction to its session group
        grouped_transactions[tx.session_id].append(tx_response)
        
        # Since the list is sorted timestamp DESC (newest first),
        # the *last* transaction we see for a session_id is the earliest one.
        session_start_times[tx.session_id] = tx.timestamp
        
    # --- Combine the lists and start times into the final response ---
    final_response: Dict[str, SessionTransactionGroup] = {}
    for session_id, tx_list in grouped_transactions.items():
        final_response[session_id] = SessionTransactionGroup(
            session_start_time=session_start_times[session_id],
            transactions=tx_list
        )
        
    return final_response


# --- Helper Function (Groups by Tool Name) ---

def _group_transactions_by_tool(results: List[Transaction]) -> Dict[str, List[TransactionResponse]]:
    """
    Helper function to parse, validate, and group a list of
    Transaction objects into a dictionary keyed by tool_name.
    """
    grouped_transactions = defaultdict(list)
    
    for tx in results:
        # Manually parse JSON strings from DB into dictionaries
        try:
            params_dict = json.loads(tx.request_params) if tx.request_params else None
        except json.JSONDecodeError:
            logger.warning(f"Could not parse request_params JSON for tx_id {tx.id}")
            params_dict = {"error": "invalid_json"}

        try:
            response_dict = json.loads(tx.response_data) if tx.response_data else None
        except json.JSONDecodeError:
            logger.warning(f"Could not parse response_data JSON for tx_id {tx.id}")
            response_dict = {"error": "invalid_json"}

        # Create the Pydantic response object
        tx_response = TransactionResponse(
            id=tx.id,
            user_id=tx.user_id,
            session_id=tx.session_id,
            server_name=tx.server_name,
            jsonrpc_method=tx.jsonrpc_method,
            request_params=params_dict,
            status=tx.status,
            response_data=response_dict,
            tool_name=tx.tool_name,
            tool_config_id=tx.tool_config_id, # <-- ADDED
            timestamp=tx.timestamp,
            start_timestamp=getattr(tx, 'start_timestamp', None),
            end_timestamp=getattr(tx, 'end_timestamp', None),
            latency_seconds=tx.latency_seconds
        )
        
        # Group by tool_name, using a placeholder for None
        key = tx_response.tool_name if tx_response.tool_name else "_unknown_tool"
        grouped_transactions[key].append(tx_response)
        
    return grouped_transactions

# --- NEW: Helper Function (Parses a simple list) ---

def _parse_transactions_list(results: List[Transaction]) -> List[TransactionResponse]:
    """
    Helper function to parse and validate a list of Transaction
    objects into a list of TransactionResponse objects.
    """
    transaction_list = []
    
    for tx in results:
        # Manually parse JSON strings from DB into dictionaries
        try:
            params_dict = json.loads(tx.request_params) if tx.request_params else None
        except json.JSONDecodeError:
            logger.warning(f"Could not parse request_params JSON for tx_id {tx.id}")
            params_dict = {"error": "invalid_json"}

        try:
            response_dict = json.loads(tx.response_data) if tx.response_data else None
        except json.JSONDecodeError:
            logger.warning(f"Could not parse response_data JSON for tx_id {tx.id}")
            response_dict = {"error": "invalid_json"}

        # Create the Pydantic response object
        tx_response = TransactionResponse(
            id=tx.id,
            user_id=tx.user_id,
            session_id=tx.session_id,
            server_name=tx.server_name,
            jsonrpc_method=tx.jsonrpc_method,
            request_params=params_dict,
            status=tx.status,
            response_data=response_dict,
            tool_name=tx.tool_name,
            tool_config_id=tx.tool_config_id, # <-- ADDED
            timestamp=tx.timestamp,
            start_timestamp=getattr(tx, 'start_timestamp', None),
            end_timestamp=getattr(tx, 'end_timestamp', None),
            latency_seconds=tx.latency_seconds
        )
        
        transaction_list.append(tx_response)
        
    return transaction_list


# --- API Endpoints ---

@router.get(
    "/transactions",
    summary="Get all Transactions"
)
def get_session_transactions(
    user_id: str = Query(..., description="The ID of the user to fetch transactions for."),
    format: Optional[str] = Query(None, description="Response format: 'json' or 'toon'"),
    db: Session = Depends(get_db)
):
    """
    Fetches all transactions for a user.
    """
    from app.utils.toon import to_toon
    from fastapi.responses import Response

    query = (
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.timestamp.desc())
    )
    results = db.execute(query).scalars().all()
    
    grouped = _group_transactions_by_session(list(results))

    if format == "toon":
        flat_tx = []
        for session_id, group in grouped.items():
            for tx in group.transactions:
                t_dict = tx.model_dump()
                t_dict["session_id"] = session_id
                flat_tx.append(t_dict)
        return Response(content=to_toon(flat_tx), media_type="text/plain")
    
    return grouped
    
    try:
        # --- 1. Build the query ---
        query = (
            select(Transaction)
            .where(
                Transaction.user_id == user_id
            )
            .order_by(Transaction.timestamp.desc())  # Sort by most recent first
        )
            
        # --- 2. Execute the query ---
        results = db.execute(query).scalars().all()
        
        # --- 3. Group results by session id ---
        return _group_transactions_by_session(results) 

    except Exception as e:
        logger.error(f"Error fetching transactions for user_id {user_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="An error occurred while fetching transactions."
        )

# --- NEW ENDPOINT: BY TOOL ---
@router.get(
    "/transactions/by_tool", 
    response_model=List[TransactionResponse],
    summary="Get Latencies for a Specific Tool"
)
def get_tool_latency_by_id(
    user_id: str = Query(..., description="The ID of the user to fetch transactions for."),
    tool_id: uuid.UUID = Query(..., description="The exact tool_id to fetch transactions for."),
    db: Session = Depends(get_db)
):
    """
    Fetches all 'tools/call' transactions for a specific user and tool_id
    that have latency data, returned as a single list.
    
    - Only returns transactions where latency_seconds is not null.
    - The list is sorted by timestamp (most recent first).
    """
    tool_name = "" # Initialize for error logging
    try:
        # --- 1. Find the tool_name from the tool_id and user_id ---
        tool_name_query = select(Tool.name).where(
            Tool.id == tool_id,
            Tool.user_id == user_id
        )
        tool_name = db.execute(tool_name_query).scalar_one_or_none()
        
        if not tool_name:
            raise HTTPException(
                status_code=404, 
                detail=f"Tool with id {tool_id} not found for user {user_id}."
            )

        # --- 2. Build the query using the found tool_name ---
        query = (
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.tool_name == tool_name,
                Transaction.jsonrpc_method == "tools/call",
                Transaction.latency_seconds != None
            )
            .order_by(Transaction.timestamp.desc())
        )
            
        # --- 3. Execute the query ---
        results = db.execute(query).scalars().all()
        
        # --- 4. Parse results into a flat list ---
        return _parse_transactions_list(results)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error fetching transactions for tool_id '{tool_id}' (name: '{tool_name}') and user '{user_id}': {e}")
        raise HTTPException(
            status_code=500, 
            detail="An error occurred while fetching tool transactions."
        )

# --- NEW ENDPOINT: TOOL USAGE ---
@router.get(
    "/transactions/tool_usage", 
    response_model=List[ToolUsageCount],
    summary="Get Most Used Tools for a User"
)
def get_tool_usage(
    user_id: str = Query(..., description="The ID of the user to fetch usage stats for."),
    db: Session = Depends(get_db)
):
    """
    Fetches the usage count for each tool for the specified user.
    Only counts transactions where jsonrpc_method is 'tools/call'.
    The result is sorted by most used tool first.
    """
    try:
        query = (
            select(Transaction.tool_name, func.count(Transaction.id).label("count"))
            .where(
                Transaction.user_id == user_id,
                Transaction.jsonrpc_method == "tools/call",
                Transaction.tool_name != None
            )
            .group_by(Transaction.tool_name)
            .order_by(func.count(Transaction.id).desc())
        )
        
        results = db.execute(query).all()
        return [{"tool_name": r.tool_name, "count": r.count} for r in results]

    except Exception as e:
        logger.error(f"Error fetching tool usage for user_id {user_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail="An error occurred while fetching tool usage statistics."
        )

