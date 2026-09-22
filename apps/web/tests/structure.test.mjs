import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { readFile, rm, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";

const execFileAsync = promisify(execFile);
const WEB_ROOT = fileURLToPath(new URL("..", import.meta.url));

test("package exposes required development scripts", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(pkg.scripts.dev, "next dev");
  assert.equal(pkg.scripts.typecheck, "tsc --noEmit");
  assert.equal(pkg.scripts.test, "node --test tests/*.test.mjs");
});

test("health route proxies to the API backend", async () => {
  const source = await readFile(
    new URL("../src/app/api/health/route.ts", import.meta.url),
    "utf8",
  );
  assert.match(source, /API_INTERNAL_URL/);
  assert.match(source, /\/health/);
});

test("typecheck and production build leave TypeScript project files clean", { timeout: 120_000 }, async () => {
  const tracked = ["tsconfig.json", "next-env.d.ts"];
  const before = new Map(
    await Promise.all(
      tracked.map(async (name) => [name, await readFile(new URL(`../${name}`, import.meta.url), "utf8")]),
    ),
  );
  const buildInfo = new URL("../tsconfig.tsbuildinfo", import.meta.url);
  const priorBuildInfo = await readFile(buildInfo).catch((error) => {
    if (error.code === "ENOENT") return null;
    throw error;
  });

  try {
    await execFileAsync(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "typecheck"], {
      cwd: WEB_ROOT,
    });
    await execFileAsync(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "build"], {
      cwd: WEB_ROOT,
      env: { ...process.env, NEXT_TELEMETRY_DISABLED: "1" },
    });
    if (priorBuildInfo === null) {
      await assert.rejects(
        readFile(buildInfo),
        (error) => error.code === "ENOENT",
        "production build created tsconfig.tsbuildinfo in the project root",
      );
    }
    for (const name of tracked) {
      assert.equal(
        await readFile(new URL(`../${name}`, import.meta.url), "utf8"),
        before.get(name),
        `${name} changed during production build`,
      );
    }
  } finally {
    await Promise.all(
      tracked.map((name) => writeFile(new URL(`../${name}`, import.meta.url), before.get(name))),
    );
    if (priorBuildInfo === null) {
      await rm(buildInfo, { force: true });
    } else {
      await writeFile(buildInfo, priorBuildInfo);
    }
  }
});
