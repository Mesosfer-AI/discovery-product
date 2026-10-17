import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { discoverProducts, safeExternalUrl } from "../src/features/discovery/api.ts";

const originalFetch = globalThis.fetch;
const jobId = "72a1db14-799a-4c07-9841-fb22dfca8462";
afterEach(() => { globalThis.fetch = originalFetch; });

function queuedJob() {
  return Response.json({ id: jobId, status: "queued" }, { status: 202 });
}

const result = {
  query: "Sony WH-1000XM5", total_discovered: 30, total_deduplicated: 30,
  total_verified: 5, execution_time_seconds: 93.68, provider_used: "amd",
  recommendations: [{
    rank: 1, trust_score: 80, match_score: 90, why_recommended: "Within budget.",
    pros: ["Official warranty"], cons: ["Higher price"],
    product: {
      id: "sony-1", title: "Sony WH-1000XM5", price: 4099000, currency: "IDR",
      url: "https://example.com/products/sony-1", image_url: null,
      store_name: "Erafone", rating: 4.4, review_count: 50,
    },
  }],
};

test("search rejects an unexpected immediate 200 result from the jobs endpoint", async () => {
  globalThis.fetch = async () => Response.json(result);
  await assert.rejects(discoverProducts({ query: "keyboard" }), /Respons rekomendasi tidak valid/);
});

test("search sends shopping intent to Laravel and preserves the recommendation", async () => {
  const payload = { query: "Sony WH-1000XM5", budget_max: 6000000, currency: "IDR", country: "id", limit: 5 };
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    assert.ok(options?.signal instanceof AbortSignal);
    if (options?.method === "POST") {
      assert.equal(url, "/api/v1/discover/jobs");
      assert.deepEqual(JSON.parse(String(options?.body)), payload);
      return queuedJob();
    }
    assert.equal(options?.method, "GET");
    assert.equal(url, `/api/v1/discover/jobs/${jobId}`);
    return Response.json({ status: "completed", result });
  };

  assert.deepEqual(await discoverProducts(payload, controller.signal), result);
});

test("search polls a queued job until the completed recommendation arrives", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const requests: string[] = [];
  globalThis.fetch = async (url, options) => {
    requests.push(String(url));
    if (options?.method === "POST") return Response.json({ id: jobId, status: "queued" }, { status: 202 });
    assert.equal(options?.method, "GET");
    return Response.json(requests.length === 2 ? { status: "processing" } : { status: "completed", result });
  };

  const pending = discoverProducts({ query: "keyboard" });
  await new Promise(setImmediate);
  assert.equal(requests.length, 2);
  t.mock.timers.tick(2000);
  assert.deepEqual(await pending, result);
  assert.deepEqual(requests, ["/api/v1/discover/jobs", `/api/v1/discover/jobs/${jobId}`, `/api/v1/discover/jobs/${jobId}`]);
});

for (const job of [{ id: "https://untrusted.example", status: "queued" }, { id: jobId, status: "unknown" }, null]) {
  test(`search rejects an invalid accepted job: ${JSON.stringify(job)}`, async () => {
    globalThis.fetch = async () => Response.json(job, { status: 202 });
    await assert.rejects(discoverProducts({ query: "keyboard" }), /Respons rekomendasi tidak valid/);
  });
}

for (const errorStatus of [429, 502, 503]) {
  test(`search surfaces failed job status ${errorStatus}`, async () => {
    globalThis.fetch = async (_url, options) => options?.method === "POST"
      ? Response.json({ id: jobId, status: "queued" }, { status: 202 })
      : Response.json({ status: "failed", error_status: errorStatus, message: "PRIVATE_INTERNAL_DETAIL" });
    await assert.rejects(discoverProducts({ query: "keyboard" }), errorStatus === 429
      ? /Akses ke sumber pencarian sedang dibatasi/ : /Layanan rekomendasi sedang tidak tersedia/);
  });
}

for (const state of [{ status: "unknown" }, { status: "failed", error_status: "429" }, { status: "completed", result: {} }]) {
  test(`search rejects malformed polling state: ${JSON.stringify(state)}`, async () => {
    globalThis.fetch = async (_url, options) => options?.method === "POST"
      ? Response.json({ id: jobId, status: "queued" }, { status: 202 }) : Response.json(state);
    await assert.rejects(discoverProducts({ query: "keyboard" }), /Respons rekomendasi tidak valid/);
  });
}

test("search reports a missing or expired job without continuing to poll", async () => {
  globalThis.fetch = async (_url, options) => options?.method === "POST"
    ? Response.json({ id: jobId, status: "queued" }, { status: 202 }) : Response.json({}, { status: 404 });
  await assert.rejects(discoverProducts({ query: "keyboard" }), /Layanan rekomendasi sedang tidak tersedia/);
});

test("search cancellation interrupts the polling delay", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const controller = new AbortController();
  globalThis.fetch = async (_url, options) => options?.method === "POST"
    ? Response.json({ id: jobId, status: "queued" }, { status: 202 }) : Response.json({ status: "queued" });
  const pending = discoverProducts({ query: "keyboard" }, controller.signal);
  const rejected = assert.rejects(pending, { name: "AbortError" });
  await new Promise(setImmediate);
  controller.abort();
  await rejected;
});

test("search aborts a stalled request after fifteen minutes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
    options?.signal?.addEventListener("abort", () => reject(options.signal?.reason), { once: true });
  });
  const pending = discoverProducts({ query: "keyboard" });
  const rejected = assert.rejects(pending, /Pencarian melewati batas waktu/);
  t.mock.timers.tick(15 * 60 * 1000);
  await rejected;
});

test("search stops polling after fifteen minutes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  let requests = 0;
  globalThis.fetch = async (_url, options) => {
    requests++;
    return options?.method === "POST"
      ? Response.json({ id: jobId, status: "queued" }, { status: 202 }) : Response.json({ status: "processing" });
  };
  const rejected = assert.rejects(discoverProducts({ query: "keyboard" }), /Pencarian melewati batas waktu/);
  await new Promise(setImmediate);
  t.mock.timers.tick(15 * 60 * 1000);
  await rejected;
  const stoppedAt = requests;
  t.mock.timers.tick(2000);
  await new Promise(setImmediate);
  assert.equal(requests, stoppedAt);
});

test("search cancellation interrupts an in-flight status request", async () => {
  const controller = new AbortController();
  globalThis.fetch = async (_url, options) => {
    if (options?.method === "POST") return Response.json({ id: jobId, status: "queued" }, { status: 202 });
    return new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(options.signal?.reason), { once: true });
      controller.abort();
    });
  };
  await assert.rejects(discoverProducts({ query: "keyboard" }, controller.signal), { name: "AbortError" });
});

test("search accepts an empty recommendation list", async () => {
  const empty = { ...result, recommendations: [] };
  globalThis.fetch = async (_url, options) => options?.method === "POST"
    ? queuedJob() : Response.json({ status: "completed", result: empty });

  assert.deepEqual(await discoverProducts({ query: "keyboard" }), empty);
});

for (const status of [422, 429, 500, 502, 503]) {
  test(`search surfaces HTTP ${status} without exposing backend details`, async () => {
    globalThis.fetch = async () => Response.json({ message: "PRIVATE_INTERNAL_DETAIL" }, { status });

    await assert.rejects(discoverProducts({ query: "keyboard" }), (error: Error) => {
      assert.ok(error.message.length > 0);
      assert.ok(!error.message.includes("PRIVATE_INTERNAL_DETAIL"));
      return true;
    });
  });
}

for (const [name, body] of [
  ["HTML", "<html>Gateway error</html>"],
  ["missing recommendations", { query: "keyboard" }],
  ["invalid product", { ...result, recommendations: [{ product: null }] }],
  ["invalid reasons", { ...result, recommendations: [{ ...result.recommendations[0], pros: "not a list" }] }],
]) {
  test(`search rejects malformed response: ${name}`, async () => {
    globalThis.fetch = async (_url, options) => options?.method === "POST" ? queuedJob()
      : name === "HTML" ? new Response(String(body)) : Response.json({ status: "completed", result: body });

    await assert.rejects(discoverProducts({ query: "keyboard" }), /Respons rekomendasi tidak valid/);
  });
}

test("blocked search explains that source access is restricted", async () => {
  globalThis.fetch = async () => Response.json({}, { status: 429 });

  await assert.rejects(discoverProducts({ query: "macbook" }), /Akses ke sumber pencarian sedang dibatasi/);
});

test("search preserves request cancellation", async () => {
  globalThis.fetch = async () => { throw new DOMException("Cancelled", "AbortError"); };

  await assert.rejects(discoverProducts({ query: "keyboard" }), { name: "AbortError" });
});

test("store and image links allow HTTP and HTTPS only", () => {
  assert.equal(safeExternalUrl("https://example.com/product"), "https://example.com/product");
  assert.equal(safeExternalUrl("http://example.com/image.jpg"), "http://example.com/image.jpg");
  for (const url of ["javascript:alert(1)", "data:text/html,test", "file:///C:/secret", "/relative", "bad url", null]) {
    assert.equal(safeExternalUrl(url), undefined);
  }
});
