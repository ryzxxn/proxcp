# Proxcp

Proxcp is a management platform for MCP (Model Context Protocol) servers, providing a bridge between LLMs and local/remote tools with built-in authentication, key management, and transaction logging.

## Project Structure

- `proxcp-client/`: Next.js frontend application.
- `proxcp-server/`: FastAPI backend application.

## Prerequisites

- Docker and Docker Compose
- Node.js (for local development of client)
- Python 3.11+ (for local development of server)

## Getting Started

### 1. Configure Environment Variables

Both the client and server require environment variables to function correctly. Examples are provided in each directory.

#### Backend (.env)
Copy `proxcp-server/.env.example` to `proxcp-server/.env` and fill in the values:
```env
JWT_SECRET="your_very_long_random_secret_here"
DATABASE_URL="sqlite:///data/proxcp.db"
```

#### Frontend (.env)
Copy `proxcp-client/.env.example` to `proxcp-client/.env` and fill in the values:
```env
BETTER_AUTH_SECRET="your_better_auth_secret_here"
BETTER_AUTH_URL="http://localhost:3005"
NEXT_PUBLIC_API_URL="http://localhost:8000"
```

### 2. Run with Docker

The easiest way to get everything running is using Docker Compose:

```bash
docker compose up --build
```

The client will be available at [http://localhost:3005](http://localhost:3005) and the server at [http://localhost:8000](http://localhost:8000).

## Features

- **MCP Bridge**: Connect to multiple MCP servers and expose them via a unified API.
- **Key Management**: Create and manage API keys for different tools.
- **Transaction Logging**: Real-time logging of all tool calls and responses.
- **Latency Tracking**: (New) Monitor the performance of your tool calls.
- **Tool Annotation**: (New) Customize tool names and descriptions for better LLM context.
- **Experimental TOON Mode**: (New) Token-Oriented Object Notation for reduced token usage.

## License

MIT
