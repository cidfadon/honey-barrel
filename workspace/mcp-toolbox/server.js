'use strict';

const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();

const PORT = process.env.PORT || 3001;
const WORKSPACE_DIR = process.env.WORKSPACE_DIR || '/workspace';

app.use(express.json({ limit: '2mb' }));

function resolveWorkspacePath(inputPath = '') {
  const candidate = String(inputPath || '').trim();

  if (!candidate) {
    return WORKSPACE_DIR;
  }

  const normalizedWorkspace = path.resolve(WORKSPACE_DIR);
  const resolved = candidate.startsWith('/')
    ? path.resolve(candidate)
    : path.resolve(normalizedWorkspace, candidate);

  if (resolved === normalizedWorkspace || resolved.startsWith(`${normalizedWorkspace}${path.sep}`)) {
    return resolved;
  }

  throw new Error(`Path escapes workspace: ${inputPath}`);
}

/* -------------------------------------------------------
   HEALTHCHECK (docker + hermes monitoring)
------------------------------------------------------- */
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'mcp-toolbox',
    timestamp: new Date().toISOString()
  });
});

/* -------------------------------------------------------
   MCP ENTRYPOINT
   Hermes expects JSON-RPC 2.0 over HTTP POST /mcp
------------------------------------------------------- */
app.post('/mcp', (req, res) => {
  try {
    const body = req.body || {};
    const method = body.method;
    const id = body.id ?? null;

    if (!method) {
      return res.status(400).json({
        jsonrpc: "2.0",
        id,
        error: {
          code: -32600,
          message: "Missing method"
        }
      });
    }

    /* ---------------------------------------------------
       INITIALIZE HANDSHAKE
    --------------------------------------------------- */
    if (method === 'initialize') {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2025-03-26",
          capabilities: {
            tools: {
              listChanged: false
            }
          },
          serverInfo: {
            name: "mcp-toolbox",
            version: "1.0.0"
          }
        }
      });
    }

    /* ---------------------------------------------------
       INITIALIZED NOTIFICATION (optional ack)
    --------------------------------------------------- */
    if (method === 'notifications/initialized') {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {}
      });
    }

    /* ---------------------------------------------------
       TOOLS LIST
    --------------------------------------------------- */
    if (method === 'tools/list') {
      return res.json({
        jsonrpc: "2.0",
        id,
        result: {
          tools: [
            {
              name: "list_files",
              description: "List files in workspace directory",
              inputSchema: {
                type: "object",
                properties: {
                  dir: {
                    type: "string",
                    description: "Optional subdirectory inside workspace"
                  }
                },
                required: []
              }
            },
            {
              name: "read_file",
              description: "Read a file from workspace",
              inputSchema: {
                type: "object",
                properties: {
                  path: {
                    type: "string",
                    description: "Relative file path inside workspace"
                  }
                },
                required: ["path"]
              }
            },
            {
              name: "write_file",
              description: "Write a file to workspace",
              inputSchema: {
                type: "object",
                properties: {
                  path: {
                    type: "string",
                    description: "Relative file path inside workspace"
                  },
                  content: {
                    type: "string",
                    description: "File content"
                  }
                },
                required: ["path"]
              }
            }
          ]
        }
      });
    }

    /* ---------------------------------------------------
       TOOL CALL DISPATCHER
    --------------------------------------------------- */
    if (method === 'tools/call') {
      const { name, arguments: args } = body.params || {};

      if (name === 'list_files') {
        const dir = args?.dir
          ? resolveWorkspacePath(args.dir)
          : WORKSPACE_DIR;

        const files = fs.readdirSync(dir).map(f => ({
          name: f
        }));

        return res.json({
          jsonrpc: "2.0",
          id,
          result: { files }
        });
      }

      if (name === 'read_file') {
        const filePath = resolveWorkspacePath(args.path || '');
        const content = fs.readFileSync(filePath, 'utf-8');

        return res.json({
          jsonrpc: "2.0",
          id,
          result: { content }
        });
      }

      if (name === 'write_file') {
        const filePath = resolveWorkspacePath(args.path || '');
        fs.mkdirSync(path.dirname(filePath), { recursive: true });
        fs.writeFileSync(filePath, args.content || '', 'utf-8');

        return res.json({
          jsonrpc: "2.0",
          id,
          result: { status: "written" }
        });
      }

      return res.status(404).json({
        jsonrpc: "2.0",
        id,
        error: {
          code: -32601,
          message: `Unknown tool: ${name}`
        }
      });
    }

    /* ---------------------------------------------------
       FALLBACK
    --------------------------------------------------- */
    return res.status(404).json({
      jsonrpc: "2.0",
      id,
      error: {
        code: -32601,
        message: `Unknown method: ${method}`
      }
    });

  } catch (err) {
    console.error('[MCP ERROR]', err);

    return res.status(500).json({
      jsonrpc: "2.0",
      error: {
        code: -32000,
        message: err.message
      }
    });
  }
});

/* -------------------------------------------------------
   START SERVER
------------------------------------------------------- */
app.listen(PORT, '0.0.0.0', () => {
  console.log(`[mcp-toolbox] running on :${PORT}`);
  console.log(`[mcp-toolbox] workspace: ${WORKSPACE_DIR}`);
});
