export type DiscoveryQuery = {
  query: string;
  budget_max?: number;
  currency?: string;
  limit?: number;
  country?: string;
};

export type Recommendation = {
  rank: number;
  trust_score: number;
  match_score: number;
  why_recommended: string;
  pros: string[];
  cons: string[];
  product: {
    id: string;
    title: string;
    price: number;
    currency: string;
    url: string;
    image_url?: string | null;
    store_name: string;
    rating?: number | null;
    review_count?: number | null;
  };
};

export type DiscoveryResponse = {
  query: string;
  total_discovered: number;
  total_deduplicated: number;
  total_verified: number;
  execution_time_seconds: number;
  provider_used: string;
  recommendations: Recommendation[];
};

export function safeExternalUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export async function discoverProducts(query: DiscoveryQuery, signal?: AbortSignal): Promise<DiscoveryResponse> {
  const baseUrl = (import.meta.env?.VITE_BACKEND_URL || "").replace(/\/$/, "");
  const deadline = new AbortController();
  const requestSignal = signal ? AbortSignal.any([signal, deadline.signal]) : deadline.signal;
  const timeout = setTimeout(() => deadline.abort(new DOMException(
    "Pencarian melewati batas waktu. Silakan coba lagi.", "TimeoutError",
  )), 15 * 60 * 1000);

  async function request(url: string, options: RequestInit) {
    requestSignal.throwIfAborted();
    let response: Response;
    try {
      response = await fetch(url, { ...options, signal: requestSignal });
    } catch (error) {
      requestSignal.throwIfAborted();
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      throw new Error("Tidak dapat menghubungi layanan rekomendasi. Coba lagi.");
    }
    if (!response.ok) throwForStatus(response.status);
    try {
      const data: unknown = await response.json();
      return { status: response.status, data };
    } catch {
      requestSignal.throwIfAborted();
      throw new Error("Respons rekomendasi tidak valid. Silakan coba lagi.");
    }
  }

  try {
    const accepted = await request(`${baseUrl}/api/v1/discover/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(query),
    });
    const job = accepted.data as { id?: unknown; status?: unknown } | null;
    if (accepted.status !== 202 || !job || job.status !== "queued" || typeof job.id !== "string"
      || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(job.id)) {
      throw new Error("Respons rekomendasi tidak valid. Silakan coba lagi.");
    }

    while (true) {
      const polled = await request(`${baseUrl}/api/v1/discover/jobs/${job.id}`, {
        method: "GET", headers: { Accept: "application/json" },
      });
      const state = polled.data as { status?: unknown; result?: unknown; error_status?: unknown } | null;
      if (polled.status !== 200 || !state) throw new Error("Respons rekomendasi tidak valid. Silakan coba lagi.");
      if (state.status === "completed") return parseDiscoveryResponse(state.result);
      if (state.status === "failed" && typeof state.error_status === "number" && [402, 429, 502, 503].includes(state.error_status)) {
        throwForStatus(state.error_status);
      }
      if (state.status !== "queued" && state.status !== "processing") {
        throw new Error("Respons rekomendasi tidak valid. Silakan coba lagi.");
      }
      await new Promise<void>((resolve, reject) => {
        requestSignal.throwIfAborted();
        const timer = setTimeout(() => {
          requestSignal.removeEventListener("abort", abort);
          resolve();
        }, 2000);
        const abort = () => {
          clearTimeout(timer);
          reject(requestSignal.reason);
        };
        requestSignal.addEventListener("abort", abort, { once: true });
      });
    }
  } finally {
    clearTimeout(timeout);
  }
}

function throwForStatus(status: number): never {
  if (status === 402) throw new Error("Kuota layanan pencarian habis. Hubungi pengelola untuk mengisi ulang kuota.");
  if (status === 422) throw new Error("Periksa kata kunci dan rentang harga Anda.");
  if (status === 429) throw new Error("Akses ke sumber pencarian sedang dibatasi. Silakan coba lagi nanti.");
  throw new Error("Layanan rekomendasi sedang tidak tersedia. Silakan coba lagi.");
}

function parseDiscoveryResponse(value: unknown): DiscoveryResponse {
  try {
    const data = value as DiscoveryResponse;
    if (!data || typeof data.query !== "string" || !Array.isArray(data.recommendations)
      || ![data.total_discovered, data.total_deduplicated, data.total_verified, data.execution_time_seconds]
        .every((value) => typeof value === "number" && Number.isFinite(value) && value >= 0)
      || data.recommendations.some((item) => !item || !item.product
        || typeof item.product.id !== "string" || typeof item.product.title !== "string"
        || typeof item.product.store_name !== "string" || typeof item.product.url !== "string"
        || typeof item.product.currency !== "string" || !/^[A-Z]{3}$/.test(item.product.currency)
        || typeof item.product.price !== "number" || !Number.isFinite(item.product.price) || item.product.price <= 0
        || typeof item.why_recommended !== "string"
        || ![item.rank, item.trust_score, item.match_score].every((value) => typeof value === "number" && Number.isFinite(value))
        || !Array.isArray(item.pros) || !item.pros.every((value) => typeof value === "string")
        || !Array.isArray(item.cons) || !item.cons.every((value) => typeof value === "string"))) {
      throw new Error("Invalid response");
    }
    return data;
  } catch {
    throw new Error("Respons rekomendasi tidak valid. Silakan coba lagi.");
  }
}
