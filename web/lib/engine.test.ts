// node --test against a real HTTP stub: no mocks, no test framework.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import type { AddressInfo } from "node:net";

const TEASER = { id: "t1", headline: "stub finding", impact_usd: 1, impact_hours: 0,
  evidence: ["stub"], confidence: 0.7, method: "stub", team: "teaser" };

const server = http.createServer((req, res) => {
  const ok = req.headers.authorization === "Bearer good";
  res.writeHead(ok ? 200 : 401, { "content-type": "application/json" });
  res.end(JSON.stringify(ok ? TEASER : { error: "invalid token" }));
});
await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
process.env.ENGINE_URL = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
const engine = await import("./engine.ts");
after(() => server.close());

test("200 returns the engine's finding", async () => {
  assert.deepEqual(await engine.getTeaser({ tenantId: "t", token: "good" }), TEASER);
});

test("401 is an EngineResponseError carrying the status", async () => {
  await assert.rejects(engine.getTeaser({ tenantId: "t", token: "bad" }), (e: unknown) => {
    assert.ok(e instanceof engine.EngineResponseError);
    assert.equal(e.status, 401);
    assert.match(e.message, /invalid token/);
    return true;
  });
});

test("a closed port is an EngineUnreachableError", async () => {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
  await assert.rejects(engine.getTeaser({ tenantId: "t", token: "good" }), engine.EngineUnreachableError);
});

test("ENGINE_TIMEOUT_MS must be a positive integer", () => {
  assert.equal(engine.parseTimeoutMs(undefined), 5000);
  assert.equal(engine.parseTimeoutMs("2500"), 2500);
  for (const bad of ["5s", "", "0", "-1", "1.5"]) {
    assert.throws(() => engine.parseTimeoutMs(bad), /ENGINE_TIMEOUT_MS must be a positive integer \(ms\)/);
  }
});
