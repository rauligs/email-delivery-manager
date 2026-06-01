import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const projectRoot = resolve(process.cwd(), "..");

test("silly ecosystem smoke test", async ({ page, request }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Four runnable layers, ready for product work." }),
  ).toBeVisible();

  const apiResponse = await request.get("http://127.0.0.1:8000/health");
  expect(apiResponse.ok()).toBe(true);
  expect(await apiResponse.json()).toEqual({
    status: "ok",
    service: {
      name: "api",
      status: "ok",
      detail: null,
    },
  });

  const workerOutput = execFileSync("uv", ["run", "background-worker", "worker"], {
    cwd: resolve(projectRoot, "background"),
    encoding: "utf8",
  });
  expect(workerOutput).toContain('"name":"worker"');
  expect(workerOutput).toContain('"status":"ok"');
});
