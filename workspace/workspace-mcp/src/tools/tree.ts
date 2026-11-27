import fs from "fs/promises";
import path from "path";

export type TreeOptions = {
  depth?: number;
  showHidden?: boolean;
};

export async function tree(
  dir: string,
  options: TreeOptions = {}
): Promise<string> {
  const maxDepth = options.depth ?? 3;
  const showHidden = options.showHidden ?? false;

  async function walk(current: string, level: number): Promise<string[]> {
    if (level > maxDepth) return [];

    let entries: string[];
    try {
      entries = await fs.readdir(current);
    } catch (err) {
      return [`[ERROR] Cannot read: ${current}`];
    }

    const lines: string[] = [];

    for (const entry of entries) {
      if (!showHidden && entry.startsWith(".")) continue;

      const fullPath = path.join(current, entry);

      let stat;
      try {
        stat = await fs.lstat(fullPath);
      } catch {
        lines.push(`${"  ".repeat(level)}- ${entry} [unreadable]`);
        continue;
      }

      if (stat.isSymbolicLink()) {
        lines.push(`${"  ".repeat(level)}- ${entry} -> [symlink]`);
        continue;
      }

      if (stat.isDirectory()) {
        lines.push(`${"  ".repeat(level)}📁 ${entry}/`);
        const children = await walk(fullPath, level + 1);
        lines.push(...children);
      } else if (stat.isFile()) {
        lines.push(`${"  ".repeat(level)}📄 ${entry}`);
      } else {
        lines.push(`${"  ".repeat(level)}❓ ${entry}`);
      }
    }

    return lines;
  }

  const rootName = path.basename(path.resolve(dir));
  const output = [`📁 ${rootName}/`];

  const treeLines = await walk(dir, 1);
  output.push(...treeLines);

  return output.join("\n");
}
