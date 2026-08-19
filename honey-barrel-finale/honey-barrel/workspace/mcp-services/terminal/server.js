import { exec } from "child_process";
import express from "express";

const app = express();
app.use(express.json());

// -------------------------
// TOOL DEFINITIONS
// -------------------------
function getTools() {
  return [
    {
      name: "terminal.exec",
      description: "Execute shell command inside /workspace sandbox",
      inputSchema: {
        type: "object",
        properties: {
          cmd: { type: "string" }
        },
        required: ["cmd"]
      }
    }
  ];
}

// -------------------------
// EXEC WRAPPER (SAFE PROMISE)
// -------------------------
function run(cmd) {
  return new Promise((resolve, reject) => {
    exec(
      cmd,
      {
        cwd: "/workspace",
        timeout: 15000,
        maxBuffer: 1024 * 1024 // 1MB stdout cap
      },
      (err, stdout, stderr) => {
        if (err) {
          return reject(stderr?.toString() || err.message);
        }
        resolve(stdout?.toString() || "");
      }
    );
  });
}

// -------------------------
// MCP ROUTER
// -------------------------
app.post("/mcp", async (req, res) => {
  const { method, id, params } = req.body || {};

  try {
    // -------------------------
    // initialize
    // -------------------------
    if (method === "initialize") {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2024-11-05",
          serverInfo: {
            name: "terminal-mcp",
            version: "1.0.0"
          },
          capabilities: {
            tools: {}
          }
        }
      });
    }

    // -------------------------
    // tools/list
    // -------------------------
    if (method === "tools/list") {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          tools: getTools()
        }
      });
    }

    // -------------------------
    // tools/call
    // -------------------------
    if (method === "tools/call") {
      const toolName = params?.name;
      const args = params?.arguments || {};

      if (toolName !== "terminal.exec") {
        return res.json({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32601,
            message: `Unknown tool: ${toolName}`
          }
        });
      }

      const cmd = args.cmd;

      if (!cmd || typeof cmd !== "string") {
        return res.json({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32602,
            message: "Invalid params: cmd must be string"
          }
        });
      }

      const output = await run(cmd);

      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          content: [
            {
              type: "text",
              text: output
            }
          ]
        }
      });
    }

    // -------------------------
    // fallback
    // -------------------------
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
        code: -32000,
        message: String(err)
      }
    });
  }
});

// -------------------------
app.listen(3000, "0.0.0.0", () => {
  console.log("terminal-mcp running on port 3000");
});
