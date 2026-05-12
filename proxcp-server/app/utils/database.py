import os
import contextlib
# --- UPDATED: Added Float, UUID ---
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, Float, UUID
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import datetime
import logging
import uuid  # <-- ADDED

load_dotenv()
logger = logging.getLogger(__name__)

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.error("DATABASE_URL not set in .env file")
    raise ValueError("DATABASE_URL not set in .env file")

# --- (MODIFIED) Configured for SQLite/Postgres with Auto-Detection ---
is_sqlite = DATABASE_URL.startswith("sqlite")

# Prepare engine arguments
engine_args = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

if is_sqlite:
    engine_args["connect_args"] = {"check_same_thread": False}
else:
    # PROD OPTIMIZATIONS for PostgreSQL/MySQL
    engine_args["pool_size"] = 20
    engine_args["max_overflow"] = 10
    engine_args["connect_args"] = {
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

engine = create_engine(DATABASE_URL, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Database Models ---

class Tool(Base):
    """
    Model for storing a SINGLE tool definition associated with a user.
    """
    __tablename__ = "tools"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # <-- UPDATED
    user_id = Column(String, index=True, nullable=False)
    name = Column(String, index=True, nullable=False)
    definition = Column(Text, nullable=True)
    server_url = Column(String, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    server_token = Column(String, nullable=True)


class UserServerConfig(Base):
    """
    Model for storing a user's server configurations.
    Each row represents one server URL and its associated token,
    corresponding to one item in the user's list of servers.
    """
    __tablename__ = "user_server_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # <-- UPDATED
    user_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=True)
    url = Column(String, index=True, nullable=False)
    token = Column(String, nullable=True)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    is_active = Column(Boolean, default=True, nullable=False)


class Transaction(Base):
    """
    Model for logging every JSON-RPC request and notification.
    """
    __tablename__ = "transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # <-- UPDATED
    user_id = Column(String, index=True, nullable=False)
    session_id = Column(String, index=True, nullable=False)
    server_name = Column(String, nullable=False)
    jsonrpc_method = Column(String, index=True, nullable=False)
    request_params = Column(Text, nullable=True)
    status = Column(String, nullable=False)
    response_data = Column(Text, nullable=True)
    tool_name = Column(String, index=True, nullable=True)
    
    # --- UPDATED: Enhanced time tracking ---
    timestamp = Column(DateTime, default=datetime.datetime.utcnow) # Still here for compatibility
    start_timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    end_timestamp = Column(DateTime, nullable=True)
    latency_seconds = Column(Float, nullable=True)
    # --- END UPDATE ---


class ApiKey(Base):
    """
    Model for storing an API key associated with a user and a tool configuration.
    """
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    tool_config_id = Column(String, index=True, nullable=False)
    key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ToolConfigMapping(Base):
    """
    Model for mapping a tool to a tool_config_id.
    """
    __tablename__ = "tool_config_mappings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_config_id = Column(String, index=True, nullable=False)
    tool_id = Column(UUID(as_uuid=True), index=True, nullable=False)

# --- DB Utility Functions ---

def check_database_connection():
    """
    Checks if the database is reachable and responsive.
    """
    logger.info("Checking database connection...")
    try:
        # Use a simple text query to verify connection
        from sqlalchemy import text
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful.")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

def check_schema():
    """
    Verify if the tables exist in the database.
    """
    logger.info("Checking database schema...")
    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected_tables = ["tools", "user_server_configs", "transactions", "api_keys", "tool_config_mappings"]
        
        missing_tables = [t for t in expected_tables if t not in tables]
        
        if not missing_tables:
            logger.info(f"✅ Schema check passed. All {len(expected_tables)} tables present.")
            return True
        else:
            logger.warning(f"⚠️ Schema check: Missing tables: {', '.join(missing_tables)}")
            return False
    except Exception as e:
        logger.error(f"❌ Schema check failed: {e}")
        return False

def create_db_and_tables():
    """
    Creates all tables defined by the Base metadata.
    Includes simple column-level migrations for existing tables.
    """
    logger.info("Initializing database...")
    if not check_database_connection():
        logger.error("Stopping database initialization due to connection failure.")
        raise ConnectionError("Could not connect to database.")

    try:
        # 1. Create tables if they don't exist
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created or verified.")

        # 2. Simple Column Migrations (for SQLite/Postgres)
        from sqlalchemy import inspect, text
        inspector = inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("transactions")]
        
        with engine.connect() as conn:
            # Add start_timestamp if missing
            if "start_timestamp" not in columns:
                logger.info("Adding 'start_timestamp' column to 'transactions' table...")
                try:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN start_timestamp DATETIME"))
                except Exception as e:
                    logger.warning(f"Could not add start_timestamp: {e}")

            # Add end_timestamp if missing
            if "end_timestamp" not in columns:
                logger.info("Adding 'end_timestamp' column to 'transactions' table...")
                try:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN end_timestamp DATETIME"))
                except Exception as e:
                    logger.warning(f"Could not add end_timestamp: {e}")

            # Add latency_seconds if missing
            if "latency_seconds" not in columns:
                logger.info("Adding 'latency_seconds' column to 'transactions' table...")
                try:
                    # Float for SQLite/Postgres compatibility
                    col_type = "DOUBLE PRECISION" if not is_sqlite else "FLOAT"
                    conn.execute(text(f"ALTER TABLE transactions ADD COLUMN latency_seconds {col_type}"))
                except Exception as e:
                    logger.warning(f"Could not add latency_seconds: {e}")
            
            # Commit changes (SQLAlchemy 2.0 style)
            conn.commit()

        check_schema()
    except Exception as e:
        logger.error(f"❌ Error creating/migrating database tables: {e}")
        # Re-raise the exception to be caught by the lifespan handler
        raise

def get_db():
    """
    FastAPI dependency to get a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextlib.contextmanager
def get_db_context():
    """
    Context manager for manual database session handling.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

