import { execSync } from "child_process";
import express from "express";

const app = express();
app.use(express.json());

// -------------------------
// TOOL DEFINITIONS
// -------------------------
function getTools() {
  return [
    {
      name: "git.status",
      description: "Get git working tree status",
      inputSchema: {
        type: "object",
        properties: {},
        required: []
      }
    },
    {
      name: "git.log",
      description: "Get git commit history",
      inputSchema: {
        type: "object",
        properties: {
          limit: {
            type: "number",
            minimum: 1,
            maximum: 200
          }
        }
      }
    }
  ];
}

// -------------------------
// SAFE GIT EXECUTION
// -------------------------
function runGit(args) {
  return execSync(`git ${args}`, {
    encoding: "utf8",
    cwd: "/workspace",
    stdio: ["ignore", "pipe", "pipe"],
    maxBuffer: 1024 * 1024
  });
}

// -------------------------
// SANITIZERS
// -------------------------
function sanitizeLimit(limit) {
  const n = Number(limit);
  if (!Number.isFinite(n)) return 10;
  return Math.min(Math.max(n, 1), 200);
}

// -------------------------
// MCP SERVER
// -------------------------
app.post("/mcp", (req, res) => {
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
            name: process.env.MCP_NAME || "git-mcp",
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

      let output = "";

      if (toolName === "git.status") {
        output = runGit("status --porcelain --branch");
      }
      else if (toolName === "git.log") {
        const limit = sanitizeLimit(args.limit);
        output = runGit(`log --oneline -n ${limit}`);
      }
      else {
        return res.json({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32601,
            message: `Unknown tool: ${toolName}`
          }
        });
      }

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
        message: String(err?.message || err)
      }
    });
  }
});

// -------------------------
app.listen(3000, "0.0.0.0", () => {
  console.log(`${process.env.MCP_NAME || "git-mcp"} running`);
});
