import time
import logging
import json
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.utils.database import (
    Tool, ToolConfigMapping, UserServerConfig, Resource, Prompt, 
    ResourceConfigMapping, PromptConfigMapping, get_db_context
)

logger = logging.getLogger(__name__)

class ToolCache:
    def __init__(self, refresh_interval: int = 300): # Refresh every 5 minutes
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {} 
        self._resources_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._prompts_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._last_refresh: Dict[str, float] = {} 
        self.refresh_interval = refresh_interval

    def get_tools(self, user_id: str, tool_config_id: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        self._maybe_refresh(user_id, force_refresh)
        return self._filter_items(self._tools_cache.get(user_id, []), tool_config_id)

    def get_resources(self, user_id: str, tool_config_id: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        self._maybe_refresh(user_id, force_refresh)
        return self._filter_items(self._resources_cache.get(user_id, []), tool_config_id)

    def get_prompts(self, user_id: str, tool_config_id: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        self._maybe_refresh(user_id, force_refresh)
        prompts = self._prompts_cache.get(user_id, [])
        filtered_prompts = self._filter_items(prompts, tool_config_id)
        logger.debug(f"Cache: Found {len(filtered_prompts)} prompts for user {user_id} (config: {tool_config_id})")
        return filtered_prompts

    def _maybe_refresh(self, user_id: str, force_refresh: bool):
        now = time.time()
        if force_refresh or user_id not in self._last_refresh or now - self._last_refresh.get(user_id, 0) > self.refresh_interval:
            logger.info(f"Refreshing cache from DB for user {user_id}")
            self._refresh_user_data(user_id)
            self._last_refresh[user_id] = now

    def _refresh_user_data(self, user_id: str):
        """Fetches all tools, resources, and prompts for a user from the DB."""
        with get_db_context() as db:
            # 1. Sync Tools
            tool_query = (
                select(Tool, UserServerConfig.name.label("server_name"))
                .outerjoin(UserServerConfig, (Tool.server_url == UserServerConfig.url) & (Tool.user_id == UserServerConfig.user_id))
                .where(Tool.user_id == user_id, Tool.is_active == True)
            )
            tool_results = db.execute(tool_query).all()
            
            tools_list = []
            for tool, server_name in tool_results:
                tool_dict = {
                    "id": str(tool.id),
                    "user_id": tool.user_id,
                    "name": tool.name,
                    "custom_name": tool.custom_name,
                    "custom_description": tool.custom_description,
                    "definition": tool.definition,
                    "server_url": tool.server_url,
                    "is_active": tool.is_active,
                    "server_name": server_name,
                    "server_token": tool.server_token
                }
                mappings = db.query(ToolConfigMapping).filter(ToolConfigMapping.tool_id == tool.id).all()
                tool_dict["mapped_config_ids"] = [m.tool_config_id for m in mappings]
                tools_list.append(tool_dict)
            self._tools_cache[user_id] = tools_list

            # 2. Sync Resources
            res_query = (
                select(Resource, UserServerConfig.name.label("server_name"))
                .outerjoin(UserServerConfig, (Resource.server_url == UserServerConfig.url) & (Resource.user_id == UserServerConfig.user_id))
                .where(Resource.user_id == user_id, Resource.is_active == True)
            )
            res_results = db.execute(res_query).all()
            
            res_list = []
            for r, sname in res_results:
                res_dict = {
                    "id": str(r.id),
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mimeType": r.mime_type,
                    "server_url": r.server_url,
                    "server_name": sname,
                    "is_template": r.is_template
                }
                mappings = db.query(ResourceConfigMapping).filter(ResourceConfigMapping.resource_id == r.id).all()
                res_dict["mapped_config_ids"] = [m.tool_config_id for m in mappings]
                res_list.append(res_dict)
            self._resources_cache[user_id] = res_list

            # 3. Sync Prompts
            p_query = (
                select(Prompt, UserServerConfig.name.label("server_name"))
                .outerjoin(UserServerConfig, (Prompt.server_url == UserServerConfig.url) & (Prompt.user_id == UserServerConfig.user_id))
                .where(Prompt.user_id == user_id, Prompt.is_active == True)
            )
            p_results = db.execute(p_query).all()
            
            p_list = []
            for p, sname in p_results:
                p_dict = {
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description,
                    "arguments": json.loads(p.arguments) if p.arguments else [],
                    "server_url": p.server_url,
                    "server_name": sname
                }
                mappings = db.query(PromptConfigMapping).filter(PromptConfigMapping.prompt_id == p.id).all()
                p_dict["mapped_config_ids"] = [m.tool_config_id for m in mappings]
                p_list.append(p_dict)
            self._prompts_cache[user_id] = p_list

    def _filter_items(self, items: List[Dict[str, Any]], tool_config_id: Optional[str]) -> List[Dict[str, Any]]:
        if not tool_config_id:
            return items
        return [i for i in items if tool_config_id in i.get("mapped_config_ids", [])]

    def invalidate(self, user_id: str):
        self._tools_cache.pop(user_id, None)
        self._resources_cache.pop(user_id, None)
        self._prompts_cache.pop(user_id, None)
        self._last_refresh.pop(user_id, None)
        logger.debug(f"Invalidated cache for user {user_id}")

tool_cache = ToolCache()
tool_cache = ToolCache()
