export const tools = [
  {
    name: "list_directory",
    description: "List files in directory",
    inputSchema: {
      type: "object",
      properties: {
        dir: { type: "string" },
      },
      required: ["dir"],
    },
  },

  {
    name: "read_file",
    description: "Read file content",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
      },
      required: ["path"],
    },
  },

  {
    name: "write_file",
    description: "Write file content",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
        content: { type: "string" },
      },
      required: ["path", "content"],
    },
  },

  {
    name: "search_files",
    description: "Search files by name",
    inputSchema: {
      type: "object",
      properties: {
        dir: { type: "string" },
        query: { type: "string" },
      },
      required: ["dir", "query"],
    },
  },

  {
    name: "stat",
    description: "File stats",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string" },
      },
      required: ["path"],
    },
  },

  {
    name: "tree",
    description: "Directory tree",
    inputSchema: {
      type: "object",
      properties: {
        dir: { type: "string" },
        depth: { type: "number" },
      },
      required: ["dir"],
    },
  },
];

