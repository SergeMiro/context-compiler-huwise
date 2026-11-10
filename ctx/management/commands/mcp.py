import os

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the MCP server (streamable HTTP). 127.0.0.1 by default; the public container binds 0.0.0.0."

    def add_arguments(self, p):
        p.add_argument("--port", type=int, default=8796)
        p.add_argument("--host", default="127.0.0.1")

    def handle(self, port, host, **_):
        from mcp.server.transport_security import TransportSecuritySettings

        from mcpserver import server
        # behind a reverse proxy the Host header is the public name: allow it explicitly (DNS-rebinding protection)
        hosts = [h for h in os.environ.get("CTXC_MCP_ALLOWED_HOSTS", "").split(",") if h]
        security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts + [f"127.0.0.1:{port}", f"localhost:{port}"],
            allowed_origins=[f"https://{h}" for h in hosts]) if hosts else None
        self.stdout.write(f"MCP on http://{host}:{port}/mcp")
        server.run("streamable-http", host=host, port=port, transport_security=security)
