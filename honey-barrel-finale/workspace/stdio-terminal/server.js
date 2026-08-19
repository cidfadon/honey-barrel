import express from "express";
import { execSync } from "child_process";
import { randomUUID } from "crypto";

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || "3002", 10);
const WORKSPACE = process.env.WORKSPACE_DIR || "/workspace";

// ---------------------------------------------------------------------------
// SSE stream (required by MCP Streamable HTTP transport)
// ---------------------------------------------------------------------------
const clients = new Map();

app.get("/mcp", (_req, res) => {
  const id = randomUUID();
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.write(`data: ${JSON.stringify({ type: "connected", id })}\n\n`);
  clients.set(id, res);
  _req.on("close", () => clients.delete(id));
});

// ---------------------------------------------------------------------------
// Health check
// ---------------------------------------------------------------------------
app.get("/health", (_req, res) => res.json({ status: "ok" }));

// ---------------------------------------------------------------------------
// MCP JSON-RPC handler
// ---------------------------------------------------------------------------
app.post("/mcp", (req, res) => {
  const msg = req.body;

  // initialize
  if (msg.method === "initialize") {
    return res.json({
      jsonrpc: "2.0",
      id: msg.id,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "mcp-terminal", version: "1.0.0" },
      },
    });
  }

  // tools/list
  if (msg.method === "tools/list") {
    return res.json({
      jsonrpc: "2.0",
      id: msg.id,
      result: {
        tools: [
          {
            name: "terminal",
            description:
              "Execute a shell command and return its stdout/stderr. " +
              "The command runs inside a Linux container with access to " +
              "the /workspace directory and the host Docker engine.",
            inputSchema: {
              type: "object",
              properties: {
                command: {
                  type: "string",
                  description: "The shell command to execute",
                },
              },
              required: ["command"],
            },
          },
        ],
      },
    });
  }

  // tools/call
  if (msg.method === "tools/call") {
    const { name, arguments: args } = msg.params;

    if (name !== "terminal") {
      return res.json({
        jsonrpc: "2.0",
        id: msg.id,
        result: {
          content: [{ type: "text", text: `Unknown tool: ${name}` }],
          isError: true,
        },
      });
    }

    const cmd = args?.command;
    if (!cmd) {
      return res.json({
        jsonrpc: "2.0",
        id: msg.id,
        result: {
          content: [{ type: "text", text: "Missing required argument: command" }],
          isError: true,
        },
      });
    }

    try {
      const output = execSync(cmd, {
        cwd: WORKSPACE,
        timeout: 120_000,
        maxBuffer: 4 * 1024 * 1024,
        encoding: "utf-8",
        shell: "/bin/bash",
        env: { ...process.env, PATH: "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" },
      });

      return res.json({
        jsonrpc: "2.0",
        id: msg.id,
        result: {
          content: [{ type: "text", text: output || "(no output)" }],
        },
      });
    } catch (err) {
      const stderr = err.stderr || "";
      const stdout = err.stdout || "";
      const code = err.status ?? 1;
      const combined = `${stdout}${stderr}`.trim() || err.message;

      return res.json({
        jsonrpc: "2.0",
        id: msg.id,
        result: {
          content: [
            { type: "text", text: `exit code ${code}\n${combined}` },
          ],
          isError: true,
        },
      });
    }
  }

  // fallback
  return res.json({
    jsonrpc: "2.0",
    id: msg.id,
    error: { code: -32601, message: "Method not found" },
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`MCP Terminal server running on :${PORT}`);
});
