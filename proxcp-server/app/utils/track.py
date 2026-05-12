import json
import logging
import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

# Import the Transaction model from the database file
from app.utils.database import Transaction 

# Get a logger instance
logger = logging.getLogger(__name__)

def log_transaction(
    db: Session,
    user_id: str,
    session_id: str,
    server_name: str,
    method: str,
    params: Optional[Dict[str, Any]],
    status: str = "accepted",
    response_data: Optional[Dict[str, Any]] = None,
    tool_name: Optional[str] = None,
    tool_config_id: Optional[str] = None, # <-- ADDED
    latency_seconds: Optional[float] = None,
    start_timestamp: Optional[datetime.datetime] = None,
    end_timestamp: Optional[datetime.datetime] = None
):
    """
    Creates and saves a transaction record in the database.
    """
    try:
        import datetime
        
        # Convert params and response dictionaries to JSON strings for storage
        params_str = json.dumps(params) if params else None
        
        # Ensure we don't try to JSON serialize non-dict objects (like fastmcp objects)
        if response_data is not None and not isinstance(response_data, (dict, list, str, int, float, bool)):
            try:
                # If it has a model_dump or similar, use it
                if hasattr(response_data, "model_dump"):
                    response_str = json.dumps(response_data.model_dump())
                else:
                    response_str = str(response_data)
            except:
                response_str = str(response_data)
        else:
            response_str = json.dumps(response_data) if response_data else None

        # Create a new Transaction object with all the data
        db_transaction = Transaction(
            user_id=user_id,
            session_id=session_id,
            server_name=server_name,
            jsonrpc_method=method,
            request_params=params_str,
            status=status,
            response_data=response_str,
            tool_name=tool_name,
            tool_config_id=tool_config_id, # <-- ADDED
            latency_seconds=latency_seconds,
            start_timestamp=start_timestamp or datetime.datetime.utcnow(),
            end_timestamp=end_timestamp or (datetime.datetime.utcnow() if latency_seconds else None)
        )

        # Add the new transaction to the session and commit to the database
        db.add(db_transaction)
        db.commit()

    except Exception as e:
        # If logging fails, roll back the transaction and log the error
        logger.error(f"Failed to log transaction: {e}")
        db.rollback()