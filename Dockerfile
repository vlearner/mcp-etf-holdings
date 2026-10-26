# Sample image for trying the HTTP transport. Not a hosting recipe: the server
# has no authentication, so publish the port to loopback only (see README).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home app

USER app
# Bind all interfaces *inside* the container; the host-side `-p 127.0.0.1:...`
# mapping is what keeps it private. The no-authentication opt-in is deliberately
# not baked in: pass `-e MCP_ALLOW_INSECURE=1` at run time (see README).
ENV MCP_TRANSPORT=http MCP_HOST=0.0.0.0 MCP_PORT=8000
EXPOSE 8000
CMD ["mcp-etf-holdings"]
