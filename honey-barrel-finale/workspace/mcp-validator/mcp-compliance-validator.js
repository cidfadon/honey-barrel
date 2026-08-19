import express from "express";
import fetch from "node-fetch";

const app = express();
app.use(express.json());

// ----------------------------
// MCP endpoint to test
// ----------------------------
const MCP_URL = process.env.MCP_URL || "http://localhost:3001";

// ----------------------------
// Validate JSON Schema shape
// ----------------------------
function validateTool(tool, index) {
  const errors = [];

  if (!tool.name) {
    errors.push("missing: name");
  }

  if (!tool.description) {
    errors.push("missing: description");
  }

  if (!tool.inputSchema) {
    errors.push("❌ CRITICAL: inputSchema missing (Hermes will FAIL)");
  } else {
    if (typeof tool.inputSchema !== "object") {
      errors.push("inputSchema must be object");
    }

    if (tool.inputSchema.type !== "object") {
      errors.push("inputSchema.type must be 'object'");
    }

    if (!tool.inputSchema.properties) {
      errors.push("inputSchema.properties missing (allowed but risky)");
    }

    if (!Array.isArray(tool.inputSchema.required)) {
      errors.push("inputSchema.required missing or invalid array");
    }
  }

  return {
    index,
    name: tool.name || "<unknown>",
    ok: errors.length === 0,
    errors
  };
}

// ----------------------------
// Fetch tools/list from MCP
// ----------------------------
async function fetchTools() {
  const res = await fetch(MCP_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: 1,
      method: "tools/list"
    })
  });

  const json = await res.json();
  return json.result?.tools || [];
}

// ----------------------------
// Main validation endpoint
// ----------------------------
app.get("/validate", async (req, res) => {
  console.log("🔍 Validating MCP server:", MCP_URL);

  try {
    const tools = await fetchTools();

    const results = tools.map(validateTool);

    const failed = results.filter(r => !r.ok);

    const summary = {
      totalTools: tools.length,
      passed: tools.length - failed.length,
      failed: failed.length,
      status: failed.length === 0 ? "PASS" : "FAIL"
    };

    res.json({
      summary,
      results
    });

  } catch (e) {
    res.status(500).json({
      error: "Validation failed",
      message: e.message
    });
  }
});

app.listen(4000, () => {
  console.log("MCP Compliance Validator running on :4000");
});
