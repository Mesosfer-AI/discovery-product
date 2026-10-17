import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { discoverProducts, safeExternalUrl } from "../src/features/discovery/api.ts";

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

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

test("search sends shopping intent to Laravel and preserves the recommendation", async () => {
  const payload = { query: "Sony WH-1000XM5", budget_max: 6000000, currency: "IDR", country: "id", limit: 5 };
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/v1/discover");
    assert.equal(options?.method, "POST");
    assert.deepEqual(JSON.parse(String(options?.body)), payload);
    assert.equal(options?.signal, controller.signal);
    return Response.json(result);
  };

  assert.deepEqual(await discoverProducts(payload, controller.signal), result);
});

test("search accepts an empty recommendation list", async () => {
  const empty = { ...result, recommendations: [] };
  globalThis.fetch = async () => Response.json(empty);

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
  ["missing recommendations", JSON.stringify({ query: "keyboard" })],
  ["invalid product", JSON.stringify({ ...result, recommendations: [{ product: null }] })],
  ["invalid reasons", JSON.stringify({ ...result, recommendations: [{ ...result.recommendations[0], pros: "not a list" }] })],
]) {
  test(`search rejects malformed response: ${name}`, async () => {
    globalThis.fetch = async () => new Response(body, { status: 200 });

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
