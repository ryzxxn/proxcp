import asyncio
import logging
from typing import Dict, Optional
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from app.utils.network import rewrite_docker_url

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages persistent connections to MCP servers.
    Reuses Client instances based on (url, token) to avoid connection overhead.
    Includes a simple cleanup mechanism to avoid memory leaks.
    """
    def __init__(self):
        # Key: (url, token), Value: (client, last_used)
        self._clients: Dict[tuple, tuple] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task = None

    async def get_client(self, url: str, token: Optional[str] = None) -> Client:
        actual_url = rewrite_docker_url(url)
        key = (actual_url, token)
        
        async with self._lock:
            # Start cleanup task if not running
            if self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

            if key in self._clients:
                client, _ = self._clients[key]
                # Check if the client session is still active
                # fastmcp Client has a 'session' attribute once entered
                is_active = False
                try:
                    if hasattr(client, "session") and client.session:
                        # Check if internal streams are closed
                        # This is a bit implementation-specific for anyio/mcp
                        is_active = True 
                except:
                    is_active = False

                if is_active:
                    self._clients[key] = (client, asyncio.get_event_loop().time())
                    return client
                else:
                    logger.info(f"Existing client for {actual_url} seems inactive, re-creating")
                    self._clients.pop(key)
                    try:
                        await client.__aexit__(None, None, None)
                    except:
                        pass
            
            logger.info(f"Creating new persistent connection to {actual_url}")
            auth_obj = BearerAuth(token) if token else None
            client = Client(actual_url, auth=auth_obj, timeout=120)
            
            try:
                await client.__aenter__()
                self._clients[key] = (client, asyncio.get_event_loop().time())
                return client
            except Exception as e:
                logger.error(f"Failed to establish connection to {actual_url}: {e}")
                raise

    async def remove_client(self, url: str, token: Optional[str] = None):
        """Removes a client from the manager, ensuring it's closed."""
        actual_url = rewrite_docker_url(url)
        key = (actual_url, token)
        async with self._lock:
            if key in self._clients:
                client, _ = self._clients.pop(key)
                logger.info(f"Removing client for {actual_url} from manager")
                try:
                    await client.__aexit__(None, None, None)
                except:
                    pass

    async def _periodic_cleanup(self):
        """Periodically close connections that haven't been used for a while."""
        while True:
            await asyncio.sleep(300) # Run every 5 minutes
            async with self._lock:
                now = asyncio.get_event_loop().time()
                to_delete = []
                for key, (client, last_used) in self._clients.items():
                    if now - last_used > 1800: # 30 minutes idle
                        to_delete.append(key)
                
                for key in to_delete:
                    client, _ = self._clients.pop(key)
                    logger.info(f"Closing idle persistent connection to {key[0]}")
                    try:
                        await client.__aexit__(None, None, None)
                    except Exception as e:
                        logger.error(f"Error closing idle client {key[0]}: {e}")

    async def close_all(self):
        async with self._lock:
            if self._cleanup_task:
                self._cleanup_task.cancel()
            for key, (client, _) in self._clients.items():
                logger.info(f"Closing persistent connection to {key[0]}")
                try:
                    await client.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"Error closing client {key[0]}: {e}")
            self._clients.clear()

connection_manager = ConnectionManager()
