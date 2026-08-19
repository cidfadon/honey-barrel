import fs from "fs/promises";

export async function listDirectory(dir: string) {
  return fs.readdir(dir);
}

