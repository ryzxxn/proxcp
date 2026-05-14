# PROXCP PROTOCOL CONSTANTS

PROTOCOL_RESOURCES = [
    {
        "uri": "file://protocol/rules",
        "name": "get_rules",
        "description": "PROXCP Protocol Rules",
        "mimeType": "text/markdown"
    }
]

PROTOCOL_TEMPLATES = [
    {
        "name": "get_weather",
        "uriTemplate": "weather://{city}/current",
        "description": "Provides mock weather information for a specific city.",
        "mimeType": "text/plain"
    },
    {
        "name": "get_path_content",
        "uriTemplate": "path://{filepath*}",
        "description": "Echoes back the path requested via wildcard.",
        "mimeType": "text/plain"
    },
    {
        "name": "search_resources",
        "uriTemplate": "api://search{?query,limit}",
        "description": "Simulates a searchable resource index with query parameters.",
        "mimeType": "text/plain"
    }
]

PROTOCOL_PROMPTS = [
    {
        "name": "explain_topic",
        "description": "Generates a simple user message asking for an explanation.",
        "arguments": [{"name": "topic", "required": True}]
    },
    {
        "name": "code_review_session",
        "description": "Sets up a structured code review conversation.",
        "arguments": [{"name": "language", "required": True}, {"name": "code", "required": True}]
    },
    {
        "name": "analyze_metrics",
        "description": "Demonstrates automatic conversion of JSON string arguments to Python types.",
        "arguments": [
            {"name": "metrics", "description": "Provide as a JSON string matching schema: array of numbers", "required": True},
            {"name": "labels", "description": "Provide as a JSON string matching schema: array of strings", "required": True},
            {"name": "metadata", "description": "Provide as a JSON string matching schema: object with string values", "required": True}
        ]
    },
    {
        "name": "system_diagnostic",
        "description": "A highly structured diagnostic prompt with runtime metadata.",
        "arguments": [{"name": "component", "required": False}]
    },
    {
        "name": "support_ticket",
        "description": "Generates a support ticket including the MCP request ID.",
        "arguments": [{"name": "issue", "required": True}]
    }
]

PROTOCOL_RULES_CONTENT = """# PROXCP PROTOCOL RULES

1. SYSTEM INTEGRITY
   - All connections must be via SSE or STDIO transport.
   - API Keys (pxp-*) must be kept confidential.

2. RESOURCE ACCESS
   - Dynamic resources are lazy-loaded on demand.
   - Resource templates require valid URI parameter replacement.

3. LLM INTERACTION
   - Use TOON format for optimized token consumption.
   - Prompts must be used for structured conversation initialization.

4. EMERGENCY PROTOCOLS
   - In case of sync failure, trigger full server refresh.
   - Transaction logs are the source of truth for audit trails.
"""
