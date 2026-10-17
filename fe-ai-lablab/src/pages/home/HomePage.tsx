import { useEffect, useMemo, useRef, useState } from "react";
import AuthModal, { type AuthMode } from "../../features/auth/AuthModal";
import { discoverProducts, type DiscoveryResponse } from "../../features/discovery/api";
import CategorySection from "./components/CategorySection";
import FlashSaleSection from "./components/FlashSaleSection";
import HeroSection from "./components/HeroSection";
import HomeHeader from "./components/HomeHeader";
import MobileNavigation from "./components/MobileNavigation";
import RecommendationsSection from "./components/RecommendationsSection";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("Semua");
  const cartCount = 0;
  const [favorites, setFavorites] = useState<string[]>([]);
  const [minPrice, setMinPrice] = useState<number | "">("");
  const [maxPrice, setMaxPrice] = useState<number | "">("");
  const [toast, setToast] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [response, setResponse] = useState<DiscoveryResponse | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const recommendations = useMemo(
    () =>
      (response?.recommendations ?? []).filter(
        ({ product }) =>
          ((minPrice === "" && maxPrice === "") || product.currency === "IDR") &&
          (minPrice === "" || product.price >= minPrice) &&
          (maxPrice === "" || product.price <= maxPrice),
      ),
    [response, maxPrice, minPrice],
  );

  const search = async (searchQuery = query) => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setIsLoading(false);
    setResponse(null);
    setError("");
    const trimmedQuery = searchQuery.trim();
    setSearchedQuery(trimmedQuery);
    document.getElementById("rekomendasi")?.scrollIntoView({ block: "start" });

    if (trimmedQuery.length < 2) {
      setError("Masukkan kata kunci minimal 2 karakter.");
      return;
    }
    if ((minPrice !== "" && !Number.isFinite(minPrice))
      || (maxPrice !== "" && (!Number.isFinite(maxPrice) || maxPrice <= 0))
      || (minPrice !== "" && maxPrice !== "" && minPrice > maxPrice)) {
      setError("Periksa rentang harga. Harga maksimum harus lebih dari 0 dan tidak kurang dari minimum.");
      return;
    }

    const controller = new AbortController();
    activeRequest.current = controller;
    setIsLoading(true);
    const timer = window.setTimeout(() => controller.abort("timeout"), 200000);
    try {
      const result = await discoverProducts({
        query: trimmedQuery,
        currency: "IDR",
        country: "id",
        limit: 5,
        ...(maxPrice !== "" ? { budget_max: maxPrice } : {}),
      }, controller.signal);
      if (activeRequest.current === controller) setResponse(result);
    } catch (cause) {
      if (activeRequest.current !== controller) return;
      if (controller.signal.aborted && controller.signal.reason !== "timeout") return;
      setError(controller.signal.reason === "timeout"
        ? "Pencarian memerlukan waktu terlalu lama. Silakan coba lagi."
        : cause instanceof Error ? cause.message : "Pencarian gagal. Silakan coba lagi.");
    } finally {
      window.clearTimeout(timer);
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setIsLoading(false);
      }
    }
  };

  const resetSearch = () => {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setQuery("");
    setSearchedQuery("");
    setCategory("Semua");
    setMinPrice("");
    setMaxPrice("");
    setResponse(null);
    setError("");
    setIsLoading(false);
  };

  const chooseCategory = (value: string) => {
    if (value === "Semua") {
      resetSearch();
      return;
    }
    setCategory(value);
    setQuery(value);
    void search(value);
  };

  const showToast = (message: string, duration = 2000) => {
    setToast(message);
    window.setTimeout(() => setToast(""), duration);
  };

  const toggleFavorite = (id: string) => {
    setFavorites((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  const completeAuth = (mode: AuthMode) => {
    setIsLoggedIn(true);
    setAuthMode(null);
    showToast(mode === "register" ? "Akun berhasil dibuat. Selamat datang!" : "Berhasil masuk. Selamat datang kembali!", 2400);
  };

  return (
    <div className="marketplace">
      <div className={`toast ${toast ? "show" : ""}`} role="status">{toast}</div>
      <HomeHeader query={query} cartCount={cartCount} isLoggedIn={isLoggedIn} isLoading={isLoading} onQueryChange={(value) => { setQuery(value); setCategory("Semua"); }} onSearch={() => void search()} onOpenAuth={setAuthMode} />

      <main>
        <HeroSection />
        <CategorySection activeCategory={category} onCategoryChange={chooseCategory} />
        {!searchedQuery && !error && <FlashSaleSection />}
        <RecommendationsSection
          category={category}
          recommendations={recommendations}
          searchedQuery={searchedQuery}
          isLoading={isLoading}
          error={error}
          response={response}
          favorites={favorites}
          minPrice={minPrice}
          maxPrice={maxPrice}
          onCategoryChange={chooseCategory}
          onFavoriteToggle={toggleFavorite}
          onSearch={() => void search()}
          onMinPriceChange={setMinPrice}
          onMaxPriceChange={setMaxPrice}
          onClearPrice={() => { setMinPrice(""); setMaxPrice(""); }}
          onReset={resetSearch}
        />
      </main>

      {authMode && (
        <AuthModal mode={authMode} onModeChange={setAuthMode} onClose={() => setAuthMode(null)} onSuccess={completeAuth} />
      )}
      <MobileNavigation cartCount={cartCount} isLoggedIn={isLoggedIn} onOpenAuth={setAuthMode} />
    </div>
  );
}
