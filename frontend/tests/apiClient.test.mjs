import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../src/services/apiClient.js", import.meta.url), "utf8")
  .replace('import axios from "axios";', "")
  .replace("import.meta.env.VITE_API_BASE_URL", '"http://test/api/v1"')
  .replace("export default apiClient;", "");

function setup(refresh) {
  const tokens = new Map([["access_token", "expired"], ["refresh_token", "valid"]]);
  let onError;
  let redirects = 0;
  const client = Object.assign(async (config) => ({ config }), {
    defaults: { baseURL: "http://test/api/v1" },
    interceptors: { request: { use() {} }, response: { use(ok, fail) { onError = fail; } } },
  });
  vm.runInNewContext(source, {
    axios: { create: () => client, post: refresh },
    localStorage: { getItem: (k) => tokens.get(k), setItem: (k, v) => tokens.set(k, v), removeItem: (k) => tokens.delete(k) },
    window: { location: { assign() { redirects++; } } },
  });
  return { tokens, run: (url = "/auth/me") => onError({ config: { url, headers: {} }, response: { status: 401 } }), redirects: () => redirects };
}

test("expired profile requests refresh and retry, sharing one refresh", async () => {
  let calls = 0;
  const app = setup(async () => { calls++; return { data: { access_token: "renewed", refresh_token: "rotated" } }; });
  const results = await Promise.all([app.run(), app.run("/customers")]);
  assert.equal(calls, 1);
  assert.equal(results[0].config.headers.Authorization, "Bearer renewed");
  assert.equal(app.tokens.get("refresh_token"), "rotated");
  assert.equal(app.redirects(), 0);
});

for (const status of [undefined, 500, 401]) {
  test(`refresh failure ${status ?? "offline"} only signs out for rejected credentials`, async () => {
    const app = setup(async () => { throw { response: status ? { status } : undefined }; });
    await assert.rejects(app.run());
    assert.equal(app.tokens.has("refresh_token"), status !== 401);
    assert.equal(app.redirects(), status === 401 ? 1 : 0);
  });
}

test("invalid login does not attempt token refresh", async () => {
  const app = setup(async () => { assert.fail("must not refresh login"); });
  await assert.rejects(app.run("/auth/login"));
  assert.equal(app.redirects(), 0);
});
