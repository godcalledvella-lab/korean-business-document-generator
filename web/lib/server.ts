import { execFile } from "node:child_process";
import { mkdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
export const projectRoot = path.join(
  /*turbopackIgnore: true*/ process.cwd(),
  "..",
);
export const sessionRoot = path.join(projectRoot, ".web-data");

export function validSession(value: string) {
  return /^[a-f0-9]{32}$/.test(value);
}

export async function ensureSessionRoot() {
  await mkdir(sessionRoot, { recursive: true });
}

export async function runPython(script: string, args: string[]) {
  try {
    const result = await execFileAsync(
      process.env.PYTHON_BIN || "python3",
      [path.join(projectRoot, "web", "scripts", script), ...args],
      {
        cwd: projectRoot,
        env: { ...process.env, PYTHONPATH: projectRoot },
        maxBuffer: 10 * 1024 * 1024,
        timeout: 10 * 60 * 1000,
      },
    );
    return JSON.parse(result.stdout);
  } catch (reason) {
    const error = reason as NodeJS.ErrnoException & {
      stderr?: string;
      stdout?: string;
    };
    throw new Error(error.stderr?.trim() || error.stdout?.trim() || error.message);
  }
}

export async function readSession(sessionId: string) {
  if (!validSession(sessionId)) return null;
  const file = path.join(sessionRoot, sessionId, "session.json");
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch {
    return null;
  }
}

export async function existingFile(file: string) {
  try {
    return (await stat(file)).isFile();
  } catch {
    return false;
  }
}
