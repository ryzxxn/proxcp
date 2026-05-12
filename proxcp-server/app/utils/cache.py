import time
import logging
import json
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.utils.database import Tool, ToolConfigMapping, UserServerConfig, get_db_context

logger = logging.getLogger(__name__)

class ToolCache:
    def __init__(self, refresh_interval: int = 300): # Refresh every 5 minutes
        self._cache: Dict[str, List[Dict[str, Any]]] = {} # user_id: [tool_dict]
        self._last_refresh: Dict[str, float] = {} # user_id: timestamp
        self.refresh_interval = refresh_interval

    def get_tools(self, user_id: str, tool_config_id: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Retrieves tools for a user. 
        If force_refresh is False and cache is < refresh_interval old, returns from memory.
        Otherwise, reads from DB.
        """
        now = time.time()
        
        # Check if we should use the cache
        # Note: We cache the full list of tools per user. 
        # Filtering by tool_config_id is done on the cached list.
        if not force_refresh and user_id in self._cache:
            if now - self._last_refresh.get(user_id, 0) < self.refresh_interval:
                logger.debug(f"Serving tools from memory for user {user_id}")
                return self._filter_tools(self._cache[user_id], tool_config_id)

        logger.info(f"Refreshing tools from DB for user {user_id}")
        all_tools = self._fetch_all_user_tools_from_db(user_id)
        self._cache[user_id] = all_tools
        self._last_refresh[user_id] = now
        
        return self._filter_tools(all_tools, tool_config_id)

    def _fetch_all_user_tools_from_db(self, user_id: str) -> List[Dict[str, Any]]:
        """Fetches all tools and their server names for a user from the DB."""
        with get_db_context() as db:
            query = (
                select(
                    Tool,
                    UserServerConfig.name.label("server_name")
                )
                .outerjoin(
                    UserServerConfig,
                    (Tool.server_url == UserServerConfig.url) &
                    (Tool.user_id == UserServerConfig.user_id)
                )
                .where(Tool.user_id == user_id)
                .where(Tool.is_active == True)
                .order_by(Tool.name)
            )
            results = db.execute(query).all()
            
            tools_list = []
            for tool, server_name in results:
                tool_dict = {
                    "id": str(tool.id),
                    "user_id": tool.user_id,
                    "name": tool.name,
                    "definition": tool.definition,
                    "server_url": tool.server_url,
                    "is_active": tool.is_active,
                    "server_name": server_name,
                    "server_token": tool.server_token
                }
                
                # Also need to know which tool_config_ids this tool is mapped to
                # for efficient filtering later.
                mappings = db.query(ToolConfigMapping).filter(ToolConfigMapping.tool_id == tool.id).all()
                tool_dict["mapped_config_ids"] = [m.tool_config_id for m in mappings]
                
                tools_list.append(tool_dict)
                
            return tools_list

    def _filter_tools(self, tools: List[Dict[str, Any]], tool_config_id: Optional[str]) -> List[Dict[str, Any]]:
        """Filters the tools based on tool_config_id if provided."""
        if not tool_config_id:
            return tools
        
        return [t for t in tools if tool_config_id in t.get("mapped_config_ids", [])]

    def invalidate(self, user_id: str):
        """Invalidates the cache for a specific user."""
        if user_id in self._cache:
            del self._cache[user_id]
        if user_id in self._last_refresh:
            del self._last_refresh[user_id]
        logger.debug(f"Invalidated tool cache for user {user_id}")

tool_cache = ToolCache()
