import path from "path";

// Workspace root inside the container — must match the volume mount.
const ROOT = path.resolve(process.env.WORKSPACE_ROOT || "/workspace");

/**
 * Resolve a caller-supplied path against the workspace root and refuse
 * anything that escapes it (path traversal, absolute paths outside ROOT,
 * sibling-prefix attacks like /workspace2/foo).
 */
export function safePath(p: string): string {
  if (typeof p !== "string" || p.length === 0) {
    throw new Error("path must be a non-empty string");
  }

  const resolved = path.resolve(ROOT, p);

  // The boundary check used to be a naive startsWith(ROOT) which let
  // `/workspace2/foo` slip through. Anchor on `ROOT + path.sep` instead.
  if (resolved !== ROOT && !resolved.startsWith(ROOT + path.sep)) {
    throw new Error(`Access denied: '${p}' is outside workspace (${ROOT})`);
  }

  return resolved;
}

export function workspaceRoot(): string {
  return ROOT;
}
