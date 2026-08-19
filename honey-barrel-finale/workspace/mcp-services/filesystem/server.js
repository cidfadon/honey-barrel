import express from "express";
import fs from "fs/promises";

const app = express();
app.use(express.json());

// -------------------------
// MCP TOOL DEFINITIONS
// -------------------------
const tools = [
  {
    name: "filesystem.read_file",
    description: "Read file content from filesystem",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" }
      },
      required: ["path"]
    }
  }
];

// -------------------------
// JSON-RPC HANDLER
// -------------------------
app.post("/mcp", async (req, res) => {
  const { id, method, params } = req.body;

  try {
    switch (method) {

      // ---- LIST TOOLS ----
      case "tools/list":
        return res.json({
          jsonrpc: "2.0",
          id,
          result: {
            tools
          }
        });

      // ---- CALL TOOL ----
      case "tools/call": {
        const { name, arguments: args } = params;

        if (name === "filesystem.read_file") {
          const content = await fs.readFile(args.path, "utf-8");

          return res.json({
            jsonrpc: "2.0",
            id,
            result: {
              content: [
                {
                  type: "text",
                  text: content
                }
              ]
            }
          });
        }

        return res.json({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32601,
            message: `Unknown tool: ${name}`
          }
        });
      }

      // ---- INITIALIZE (optional but common) ----
      case "initialize":
        return res.json({
          jsonrpc: "2.0",
          id,
          result: {
            protocolVersion: "2024-11-05",
            serverInfo: {
              name: "filesystem-mcp",
              version: "1.0.0"
            },
            capabilities: {
              tools: {}
            }
          }
        });

      default:
        return res.json({
          jsonrpc: "2.0",
          id,
          error: {
            code: -32601,
            message: `Unknown method: ${method}`
          }
        });
    }
  } catch (err) {
    return res.json({
      jsonrpc: "2.0",
      id,
      error: {
        code: -32000,
        message: err.message
      }
    });
  }
});

// -------------------------
app.listen(3000, "0.0.0.0", () => {
  console.log("filesystem-mcp running on port 3000");
});
