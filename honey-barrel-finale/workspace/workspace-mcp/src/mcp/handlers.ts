import { safePath } from "../tools/fsGuard.js";
import { listDirectory } from "../tools/listDirectory.js";
import { readFile } from "../tools/readFile.js";
import { writeFile } from "../tools/writeFile.js";
import { searchFiles } from "../tools/searchFiles.js";
import { stat } from "../tools/stat.js";
import { tree } from "../tools/tree.js";

// Every tool path/dir arg flows through safePath() so we cannot escape the
// configured workspace root (default: /workspace).

function asText(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export async function handleToolCall(req: any) {
  const { name, arguments: args = {} } = req.params ?? {};

  switch (name) {
    case "list_directory": {
      const dir = safePath(args.dir ?? ".");
      return {
        content: [{ type: "text", text: asText(await listDirectory(dir)) }],
      };
    }

    case "read_file": {
      const p = safePath(args.path);
      return {
        content: [{ type: "text", text: await readFile(p) }],
      };
    }

    case "write_file": {
      const p = safePath(args.path);
      const content = typeof args.content === "string" ? args.content : "";
      return {
        content: [
          { type: "text", text: asText(await writeFile(p, content)) },
        ],
      };
    }

    case "search_files": {
      const dir = safePath(args.dir ?? ".");
      return {
        content: [
          {
            type: "text",
            text: asText(await searchFiles(dir, args.query ?? "")),
          },
        ],
      };
    }

    case "stat": {
      const p = safePath(args.path);
      return {
        content: [{ type: "text", text: asText(await stat(p)) }],
      };
    }

    case "tree": {
      const dir = safePath(args.dir ?? ".");
      const depth = typeof args.depth === "number" ? args.depth : 3;
      return {
        content: [{ type: "text", text: asText(await tree(dir, depth)) }],
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}
