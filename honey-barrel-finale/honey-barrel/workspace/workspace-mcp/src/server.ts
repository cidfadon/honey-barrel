import express, { Request, Response, NextFunction } from "express";
import { tools } from "./mcp/tools.js";
import { handleToolCall } from "./mcp/handlers.js";
import { logger } from "./utils/logger.js";

// ---------------------------------------------------------------------------
//  workspace-mcp — HTTP MCP server (JSON-RPC 2.0 over POST /mcp)
//
//  Same wire format as mcp-toolbox so Hermes can register it with:
//    hermes mcp add workspace --url http://workspace-mcp:3001/mcp
//
//  Routes:
//    GET  /health  -> liveness probe (used by docker compose healthcheck)
//    GET  /mcp     -> SSE keep-alive stream (some MCP clients open it first)
//    POST /mcp     -> JSON-RPC 2.0 entrypoint (initialize / tools/list / tools/call)
// ---------------------------------------------------------------------------

const PORT = Number(process.env.PORT || 3001);
const HOST = process.env.HOST || "0.0.0.0";

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: any;
}

function rpcError(
  id: string | number | null | undefined,
  code: number,
  message: string,
  data?: any
) {
  return {
    jsonrpc: "2.0",
    id: id ?? null,
    error: { code, message, ...(data !== undefined ? { data } : {}) },
  };
}

function rpcResult(id: string | number | null | undefined, result: any) {
  return { jsonrpc: "2.0", id: id ?? null, result };
}

export async function startServer() {
  const app = express();
  app.use(express.json({ limit: "10mb" }));

  // -------------------------------------------------------------------------
  // health endpoint — docker compose healthcheck hits this
  // -------------------------------------------------------------------------
  app.get("/health", (_req: Request, res: Response) => {
    res.json({
      ok: true,
      service: "workspace-mcp",
      tools: tools.length,
      workspace: process.env.WORKSPACE_ROOT || "/workspace",
    });
  });

  // -------------------------------------------------------------------------
  // GET /mcp — SSE keep-alive (optional, kept for parity with mcp-toolbox)
  // -------------------------------------------------------------------------
  app.get("/mcp", (req: Request, res: Response) => {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.write(`data: ${JSON.stringify({ type: "connected" })}\n\n`);

    const ka = setInterval(() => res.write(": keep-alive\n\n"), 15000);
    req.on("close", () => clearInterval(ka));
  });

  // -------------------------------------------------------------------------
  // POST /mcp — JSON-RPC 2.0 entrypoint
  // -------------------------------------------------------------------------
  app.post("/mcp", async (req: Request, res: Response) => {
    const msg = req.body as JsonRpcRequest;

    if (!msg || msg.jsonrpc !== "2.0" || typeof msg.method !== "string") {
      return res.status(400).json(rpcError(msg?.id, -32600, "Invalid Request"));
    }

    logger.debug(`MCP REQUEST: ${msg.method}`, { id: msg.id });

    try {
      switch (msg.method) {
        case "initialize":
          return res.json(
            rpcResult(msg.id, {
              protocolVersion: "2024-11-05",
              capabilities: { tools: {} },
              serverInfo: { name: "workspace-mcp", version: "1.0.0" },
            })
          );

        // Client-to-server notifications (no response body, but reply 200/204
        // so HTTP transports don't complain).
        case "notifications/initialized":
        case "notifications/cancelled":
          return res.status(204).end();

        case "ping":
          return res.json(rpcResult(msg.id, {}));

        case "tools/list":
          return res.json(rpcResult(msg.id, { tools }));

        case "tools/call": {
          const out = await handleToolCall({ params: msg.params ?? {} });
          return res.json(rpcResult(msg.id, out));
        }

        default:
          return res.json(
            rpcError(msg.id, -32601, `Method not found: ${msg.method}`)
          );
      }
    } catch (err: any) {
      logger.error("MCP handler error", {
        method: msg.method,
        error: err?.message ?? String(err),
      });
      return res.json(
        rpcError(msg.id, -32603, "Internal error", {
          detail: err?.message ?? String(err),
        })
      );
    }
  });

  // global express error handler (must have 4 args so express recognises it)
  app.use(
    (err: Error, _req: Request, res: Response, _next: NextFunction) => {
      logger.error("Express error", { error: err.message });
      res.status(500).json({ error: err.message });
    }
  );

  app.listen(PORT, HOST, () => {
    logger.info(`workspace-mcp HTTP listening on ${HOST}:${PORT}`);
    logger.info(
      `Tools available (${tools.length}): ${tools.map((t) => t.name).join(", ")}`
    );
    logger.info(
      `Workspace root: ${process.env.WORKSPACE_ROOT || "/workspace"}`
    );
  });
}
