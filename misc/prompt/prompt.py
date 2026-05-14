import logging
from typing import List, Dict, Optional
from fastmcp import FastMCP, Context
from fastmcp.prompts import Message, PromptResult
from pydantic import Field

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
    name="PromptTestServer"
)

# 1. Basic String Prompt
@mcp.prompt()
def explain_topic(topic: str) -> str:
    """Generates a simple user message asking for an explanation."""
    logger.info(f"Prompt requested: explain_topic(topic={topic})")
    return f"Please explain the core concepts of {topic} in simple terms."

# 2. Multi-Message Prompt (Conversation)
@mcp.prompt()
def code_review_session(language: str, code: str) -> List[Message]:
    """Sets up a structured code review conversation."""
    logger.info(f"Prompt requested: code_review_session(language={language})")
    logger.debug(f"Code provided (length): {len(code)}")
    return [
        Message(f"I have some {language} code that I need you to review for security and performance."),
        Message(f"Sure, please share the code snippet.", role="assistant"),
        Message(f"Here it is:\n\n```\n{code}\n```")
    ]

# 3. Complex Argument Types
@mcp.prompt()
def analyze_metrics(
    metrics: List[float], 
    labels: List[str], 
    metadata: Dict[str, str]
) -> str:
    """Demonstrates automatic conversion of JSON string arguments to Python types."""
    logger.info(f"Prompt requested: analyze_metrics(metrics={metrics}, labels={labels}, metadata={metadata})")
    summary = ", ".join([f"{l}: {m}" for l, m in zip(labels, metrics)])
    source = metadata.get("source", "unknown source")
    return f"Please analyze these metrics from {source}: {summary}"

# 4. Advanced PromptResult with Metadata
@mcp.prompt(
    name="system_diagnostic",
    description="A highly structured diagnostic prompt with runtime metadata.",
    tags={"debug", "system"}
)
def run_diagnostic(component: str = "all") -> PromptResult:
    """Returns a diagnostic request with rendering-time metadata."""
    logger.info(f"Prompt requested: system_diagnostic(component={component})")
    return PromptResult(
        messages=[
            Message(f"Perform a full diagnostic sweep of the following system component: {component}"),
            Message("Initializing diagnostic protocols. Accessing system logs...", role="assistant")
        ],
        description=f"Diagnostic request for {component}",
        meta={
            "priority": "high" if component == "all" else "normal",
            "environment": "production-test"
        }
    )

# 5. Using Context
@mcp.prompt()
async def support_ticket(issue: str, ctx: Context) -> str:
    """Generates a support ticket including the MCP request ID."""
    logger.info(f"Prompt requested: support_ticket(issue={issue})")
    logger.debug(f"Context Request ID: {ctx.request_id}")
    return f"New support ticket created.\nIssue: {issue}\nInternal Reference ID: {ctx.request_id}"

if __name__ == "__main__":
    # Standard FastMCP run
    mcp.run(transport="sse", host="0.0.0.0")
