import { execFile, spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
export const projectRoot = path.join(
  /*turbopackIgnore: true*/ process.cwd(),
  "..",
);
export const sessionRoot = path.join(projectRoot, ".web-data");

type WorkerRequest = {
  source: string;
  directory: string;
  original_name: string;
};

type PendingExtraction = {
  resolve: (payload: unknown) => void;
  reject: (reason: Error) => void;
};

type OcrWorker = {
  child: ChildProcessWithoutNullStreams;
  pending: PendingExtraction[];
  output: string;
  errors: string;
  queue: Promise<void>;
};

const serverGlobals = globalThis as typeof globalThis & {
  rmntcOcrWorker?: OcrWorker;
};

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

function ocrWorker() {
  if (serverGlobals.rmntcOcrWorker?.child.exitCode === null) {
    return serverGlobals.rmntcOcrWorker;
  }
  const child = spawn(
    process.env.PYTHON_BIN || "python3",
    [
      "-u",
      path.join(projectRoot, "web", "scripts", "extract_invoice.py"),
      "--worker",
      process.env.OCR_PROVIDER || "paddle",
    ],
    {
      cwd: projectRoot,
      env: { ...process.env, PYTHONPATH: projectRoot },
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  const state: OcrWorker = {
    child,
    pending: [],
    output: "",
    errors: "",
    queue: Promise.resolve(),
  };
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk: string) => {
    state.output += chunk;
    let newline = state.output.indexOf("\n");
    while (newline >= 0) {
      const line = state.output.slice(0, newline);
      state.output = state.output.slice(newline + 1);
      const pending = state.pending.shift();
      if (pending) {
        try {
          const response = JSON.parse(line);
          if (response.ok) pending.resolve(response.payload);
          else pending.reject(new Error(response.error || "OCR extraction failed."));
        } catch (reason) {
          pending.reject(reason instanceof Error ? reason : new Error(String(reason)));
        }
      }
      newline = state.output.indexOf("\n");
    }
  });
  child.stderr.on("data", (chunk: string) => {
    state.errors = (state.errors + chunk).slice(-20_000);
  });
  child.on("exit", () => {
    const error = new Error(state.errors.trim() || "OCR worker stopped unexpectedly.");
    for (const pending of state.pending.splice(0)) pending.reject(error);
    if (serverGlobals.rmntcOcrWorker === state) delete serverGlobals.rmntcOcrWorker;
  });
  serverGlobals.rmntcOcrWorker = state;
  return state;
}

export function runExtraction(request: WorkerRequest): Promise<unknown> {
  const state = ocrWorker();
  return new Promise((resolve, reject) => {
    state.queue = state.queue.then(
      () => new Promise<void>((complete) => {
        state.pending.push({
          resolve: (payload) => { resolve(payload); complete(); },
          reject: (reason) => { reject(reason); complete(); },
        });
        state.child.stdin.write(JSON.stringify(request) + "\n");
      }),
    );
  });
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

export async function writeSession(sessionId: string, session: unknown) {
  const directory = path.join(sessionRoot, sessionId);
  const destination = path.join(directory, "session.json");
  const temporary = path.join(directory, `.session.${randomUUID()}.tmp`);
  await writeFile(temporary, `${JSON.stringify(session, null, 2)}\n`, {
    encoding: "utf8",
    flag: "wx",
  });
  await rename(temporary, destination);
}

export async function existingFile(file: string) {
  try {
    return (await stat(file)).isFile();
  } catch {
    return false;
  }
}
