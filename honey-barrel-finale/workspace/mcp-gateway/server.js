import express from "express";
import fs from "fs";
import yaml from "yaml";

const app = express();
app.use(express.json());

const config = yaml.parse(
  fs.readFileSync("./config.yaml", "utf8")
);

const servers = config.servers;

// cache tools
let toolCache = [];
let toolMap = new Map();

/**
 * Fetch tools from all MCP backends at startup
 */
async function discoverTools() {
  toolCache = [];
  toolMap.clear();

  for (const [name, server] of Object.entries(servers)) {
    try {
      const res = await fetch(`${server.url}/mcp`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: 1,
          method: "tools/list",
          params: {}
        })
      });

      const json = await res.json();
      const tools = json?.result?.tools || [];

      for (const t of tools) {
        const namespaced = {
          ...t,
          name: `${name}.${t.name}`,
          _backend: name
        };

        toolCache.push(namespaced);
        toolMap.set(namespaced.name, {
          server: servers[name],
          originalName: t.name
        });
      }
    } catch (err) {
      console.error(`[discovery] ${name} failed`, err.message);
    }
  }

  console.log(`[gateway] discovered tools: ${toolCache.length}`);
}

// initial discovery
await discoverTools();

app.get("/health", (_, res) => {
  res.json({ status: "ok" });
});

/**
 * MCP ENTRYPOINT (ONLY JSON-RPC)
 */
app.post("/mcp", async (req, res) => {
  const { method, id, params } = req.body;

  try {
    /**
     * 1. initialize
     */
    if (method === "initialize") {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: {
            name: "mcp-gateway",
            version: "2.0.0"
          }
        }
      });
    }

    /**
     * 2. tools/list (dynamic aggregation)
     */
    if (method === "tools/list") {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          tools: toolCache,
          nextCursor: null
        }
      });
    }

    /**
     * 3. tools/call (dynamic routing)
     */
    if (method === "tools/call") {
      const toolName = params?.name;
      const tool = toolMap.get(toolName);

      if (!tool) {
        return res.json({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32601,
            message: `Tool not found: ${toolName}`
          }
        });
      }

      const backendReq = {
        jsonrpc: "2.0",
        id,
        method: "tools/call",
        params: {
          name: tool.originalName,
          arguments: params?.arguments || {}
        }
      };

      const response = await fetch(`${tool.server.url}/mcp`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(backendReq)
      });

      const data = await response.json();
      return res.json(data);
    }

    /**
     * fallback
     */
    return res.json({
      jsonrpc: "2.0",
      id,
      error: {
        code: -32601,
        message: `Unknown method: ${method}`
      }
    });

  } catch (err) {
    return res.json({
      jsonrpc: "2.0",
      id,
      error: {
        code: -32603,
        message: err.message
      }
    });
  }
});

app.listen(3002, "0.0.0.0", () => {
  console.log("MCP Gateway v2 listening on 3002");
});
