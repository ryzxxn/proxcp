from fastapi import FastAPI, Request, HTTPException # type: ignore
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
import logging
import aiohttp
from typing import Optional
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager
from app.routers.mcp.route import router as mcp_router
from app.routers.sync.route import router as sync_router
from app.routers.tool.route import router as tool_router
from app.routers.transaction.route import router as transaction_router
from app.routers.api_key.route import router as api_key_router
# --- CHANGE 1: Import the correct function name ---
from app.utils.database import create_db_and_tables

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database on startup
    logger.info("🚀 Starting Proxcp Server...")
    try:
        create_db_and_tables()  # Initialize database tables
        logger.info("✅ Server startup sequence completed")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {str(e)}")
    
    yield
    # Log shutdown event
    logger.info("🛑 Shutting down server")
    try:
        from app.utils.connections import connection_manager
        await connection_manager.close_all()
        logger.info("✅ All persistent connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)

# Add CORS middleware (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGINS", "*")],  # Use environment variable or allow all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the routers
app.include_router(mcp_router, tags=["mcp"])
app.include_router(sync_router, tags=["sync"])
app.include_router(tool_router, tags=["tool"])
app.include_router(transaction_router, tags=["transaction"])
app.include_router(api_key_router, tags=["api_key"])

if __name__ == "__main__":
    import uvicorn
    # Run the FastAPI app with Uvicorn
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )