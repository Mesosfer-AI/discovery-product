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
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/v1/discover`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(query),
      signal,
    });
  } catch (error) {
    if (signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
    throw new Error("Tidak dapat menghubungi layanan rekomendasi. Coba lagi.");
  }

  if (!response.ok) {
    if (response.status === 422) throw new Error("Periksa kata kunci dan rentang harga Anda.");
    if (response.status === 429) throw new Error("Akses ke sumber pencarian sedang dibatasi. Silakan coba lagi nanti.");
    throw new Error("Layanan rekomendasi sedang tidak tersedia. Silakan coba lagi.");
  }

  try {
    const data = await response.json() as DiscoveryResponse;
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
