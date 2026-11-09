from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the MCP server (streamable HTTP) on 127.0.0.1"

    def add_arguments(self, p):
        p.add_argument("--port", type=int, default=8796)

    def handle(self, port, **_):
        from mcpserver import server
        self.stdout.write(f"MCP on http://127.0.0.1:{port}/mcp")
        server.run("streamable-http", host="127.0.0.1", port=port)
