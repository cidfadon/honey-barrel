import fs from "fs/promises";

export async function searchFiles(dir: string, query: string) {
  const files = await fs.readdir(dir);
  return files.filter((f) => f.includes(query));
}

