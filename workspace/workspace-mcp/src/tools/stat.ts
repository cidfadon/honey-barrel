import fs from "fs/promises";

export async function stat(path: string) {
  const s = await fs.stat(path);

  return {
    size: s.size,
    isFile: s.isFile(),
    isDirectory: s.isDirectory(),
    mtime: s.mtime,
    ctime: s.ctime,
  };
}
