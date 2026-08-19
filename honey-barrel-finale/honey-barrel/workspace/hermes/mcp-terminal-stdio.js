#!/usr/bin/env node
/**
 * Minimal MCP stdio server for Hermes's built-in Terminal tool.
 * Communicates via JSON-RPC over stdin/stdout (one JSON message per line).
 * Provides a single "terminal" tool that executes shell commands.
 */

const { execSync } = require("child_process");
const readline = require("readline");

const WORKSPACE = process.env.WORKSPACE_DIR || process.env.HERMES_WORKSPACE || "/workspace";

const rl = readline.createInterface({ input: process.stdin, terminal: false });

function respond(id, result) {
  const msg = JSON.stringify({ jsonrpc: "2.0", id, result });
  process.stdout.write(msg + "\n");
}

function respondError(id, code, message) {
  const msg = JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } });
  process.stdout.write(msg + "\n");
}

rl.on("line", (line) => {
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return;
  }

  const { id, method, params } = msg;

  switch (method) {
    case "initialize":
      respond(id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "hermes-terminal-stdio", version: "1.0.0" },
      });
      break;

    case "notifications/initialized":
      // No response needed for notifications
      break;

    case "tools/list":
      respond(id, {
        tools: [
          {
            name: "terminal",
            description: "Execute a shell command in the workspace",
            inputSchema: {
              type: "object",
              properties: {
                command: { type: "string", description: "Shell command to execute" },
              },
              required: ["command"],
            },
          },
        ],
      });
      break;

    case "tools/call": {
      const { name, arguments: args } = params || {};
      if (name !== "terminal") {
        respond(id, {
          content: [{ type: "text", text: `Unknown tool: ${name}` }],
          isError: true,
        });
        break;
      }

      const cmd = args?.command;
      if (!cmd) {
        respond(id, {
          content: [{ type: "text", text: "No command provided" }],
          isError: true,
        });
        break;
      }

      try {
        const output = execSync(cmd, {
          cwd: WORKSPACE,
          timeout: 120_000,
          maxBuffer: 4 * 1024 * 1024,
          encoding: "utf-8",
          shell: "/bin/bash",
          env: {
            ...process.env,
            PATH: "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
          },
        });
        respond(id, {
          content: [{ type: "text", text: output || "(no output)" }],
        });
      } catch (err) {
        const stderr = err.stderr || "";
        const stdout = err.stdout || "";
        const text = stderr || stdout || err.message || "Command failed";
        respond(id, {
          content: [{ type: "text", text: `${text}\n(exit code ${err.status || 1})` }],
          isError: true,
        });
      }
      break;
    }

    default:
      if (id !== undefined) {
        respondError(id, -32601, `Method not found: ${method}`);
      }
  }
});
