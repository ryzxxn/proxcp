import json
import logging
from pathlib import Path
from fastmcp import FastMCP, Context
from fastmcp.resources import ResourceResult, ResourceContent, FileResource

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Explicitly set low-level MCP logging to DEBUG
logging.getLogger("mcp").setLevel(logging.DEBUG)
logging.getLogger("fastmcp").setLevel(logging.DEBUG)

# Create FastMCP server
mcp = FastMCP(
    name="ResourceTestServer"
)

# 0. Static File Resource
rules_path = Path(__file__).parent / "rules.txt"
if rules_path.exists():
    logger.debug(f"Registering static file resource from {rules_path}")
    mcp.add_resource(
        FileResource(
            uri="file://protocol/rules",
            path=rules_path,
            name="Protocol Rules",
            description="System-wide operational rules and guidelines.",
            mime_type="text/markdown"
        )
    )

# 1. Basic Static Resource
@mcp.resource("resource://greeting")
def get_greeting() -> str:
    """Provides a simple greeting message."""
    logger.info("Resource requested: resource://greeting")
    return "Hello from the Proxcp Resource Test Server!"

# 2. JSON Resource
@mcp.resource("data://config")
def get_config() -> str:
    """Provides test configuration data as JSON."""
    logger.info("Resource requested: data://config")
    data = {
        "status": "testing",
        "features": ["static_resources", "templates", "query_params"],
        "version": "1.0.0"
    }
    logger.debug(f"Returning config: {data}")
    return json.dumps(data)

# 3. Resource Template with Path Parameters
@mcp.resource("weather://{city}/current")
def get_weather(city: str) -> str:
    """Provides mock weather information for a specific city."""
    logger.info(f"Resource requested: weather://{city}/current")
    data = {
        "city": city.capitalize(),
        "temperature": 22,
        "condition": "Sunny",
        "unit": "celsius"
    }
    logger.debug(f"Returning weather data: {data}")
    return json.dumps(data)

# 4. Resource Template with Wildcard Path Parameters
@mcp.resource("path://{filepath*}")
def get_path_content(filepath: str) -> str:
    """Echoes back the path requested via wildcard."""
    logger.info(f"Resource requested: path://{filepath}")
    return f"You requested access to the virtual path: {filepath}"

# 5. Resource Template with Query Parameters
@mcp.resource("api://search{?query,limit}")
def search_resources(query: str = "all", limit: int = 10) -> dict:
    """Simulates a searchable resource index with query parameters."""
    logger.info(f"Resource requested: api://search?query={query}&limit={limit}")
    results = [
        {"id": i, "name": f"Result {i} for {query}"} 
        for i in range(min(limit, 5))
    ]
    logger.debug(f"Found {len(results)} results")
    return {
        "query": query,
        "limit": limit,
        "results": results
    }

# 6. Advanced ResourceResult (Multi-content)
@mcp.resource("data://manifest")
def get_manifest() -> ResourceResult:
    """Returns a manifest in both JSON and Markdown formats."""
    logger.info("Resource requested: data://manifest")
    return ResourceResult(
        contents=[
            ResourceContent(
                content=json.dumps({"manifest": "v1", "items": 3}), 
                mime_type="application/json"
            ),
            ResourceContent(
                content="# System Manifest\n- Item 1\n- Item 2\n- Item 3", 
                mime_type="text/markdown"
            ),
        ],
        meta={"server": "resource-test-01"}
    )

if __name__ == "__main__":
    # Standard FastMCP run
    mcp.run(transport="sse", host="0.0.0.0")
