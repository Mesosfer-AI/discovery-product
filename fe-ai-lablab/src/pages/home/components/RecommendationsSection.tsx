import Icon from "../../../components/ui/Icon";
import { safeExternalUrl, type DiscoveryResponse, type Recommendation } from "../../../features/discovery/api";
import PriceRangeFilter from "./PriceRangeFilter";

type RecommendationsSectionProps = {
  category: string;
  recommendations: Recommendation[];
  searchedQuery: string;
  isLoading: boolean;
  error: string;
  response: DiscoveryResponse | null;
  favorites: string[];
  minPrice: number | "";
  maxPrice: number | "";
  onCategoryChange: (category: string) => void;
  onFavoriteToggle: (id: string) => void;
  onSearch: () => void;
  onMinPriceChange: (value: number | "") => void;
  onMaxPriceChange: (value: number | "") => void;
  onClearPrice: () => void;
  onReset: () => void;
};

export default function RecommendationsSection({
  category,
  recommendations,
  searchedQuery,
  isLoading,
  error,
  response,
  favorites,
  minPrice,
  maxPrice,
  onCategoryChange,
  onFavoriteToggle,
  onSearch,
  onMinPriceChange,
  onMaxPriceChange,
  onClearPrice,
  onReset,
}: RecommendationsSectionProps) {
  return (
    <section className="page-width recommendations" id="rekomendasi" aria-label="Rekomendasi produk" aria-busy={isLoading}>
      <div className="recommendation-tabs">
        <button type="button" className={category === "Semua" ? "active" : ""} onClick={() => onCategoryChange("Semua")}>Rekomendasi</button>
        <button type="button" onClick={() => onCategoryChange("Fashion Wanita")}>Fashion</button>
        <button type="button" onClick={() => onCategoryChange("Rumah Tangga")}>Rumah & Living</button>
        <button type="button" onClick={() => onCategoryChange("Aksesori")}>Aksesori</button>
      </div>

      <PriceRangeFilter
        minPrice={minPrice}
        maxPrice={maxPrice}
        onMinPriceChange={onMinPriceChange}
        onMaxPriceChange={onMaxPriceChange}
        onClear={onClearPrice}
        onApply={onSearch}
        isLoading={isLoading}
      />

      <div className="discovery-heading">
        <div><h2>{searchedQuery ? `Hasil untuk “${searchedQuery}”` : "Temukan produk yang sesuai"}</h2>
          {response && !isLoading && !error && <p>{recommendations.length} rekomendasi · {response.total_discovered} kandidat ditemukan · {response.execution_time_seconds.toFixed(1)} detik</p>}
        </div>
        {(searchedQuery || error) && <button type="button" className="clear-price" onClick={onReset}>{isLoading ? "Batalkan" : "Reset pencarian"}</button>}
      </div>

      {isLoading ? (
        <div className="empty-state" role="status" aria-live="polite">
          <Icon name="search" size={30} /><h3>Sedang mencari rekomendasi…</h3>
          <p>Kami sedang mencari produk dan menilai kecocokannya. Proses ini dapat memerlukan beberapa menit.</p>
        </div>
      ) : error ? (
        <div className="empty-state" role="alert">
          <h3>Pencarian belum berhasil</h3><p>{error}</p>
          <button type="button" onClick={onSearch}>Coba lagi</button>
        </div>
      ) : recommendations.length ? (
        <div className="product-grid">
          {recommendations.map((recommendation) => {
            const { product } = recommendation;
            const favorite = favorites.includes(product.id);
            const storeUrl = safeExternalUrl(product.url);
            const imageUrl = safeExternalUrl(product.image_url);
            return (
              <article className="product-card discovery-card" key={product.id}>
                <div className="product-image">
                  {imageUrl ? <img src={imageUrl} alt={product.title} loading="lazy" /> : <div className="product-image-placeholder"><Icon name="store" size={30} /><span>Gambar belum tersedia</span></div>}
                  <span className="product-label">Pilihan #{recommendation.rank}</span>
                  <button type="button" className={`favorite ${favorite ? "active" : ""}`} onClick={() => onFavoriteToggle(product.id)} aria-pressed={favorite} aria-label={favorite ? "Hapus dari favorit" : "Tambah ke favorit"}>
                    <Icon name="heart" size={17} fill={favorite} />
                  </button>
                </div>
                <div className="product-info">
                  <h3>{product.title}</h3>
                  <span className="shop"><Icon name="store" size={12} /> {product.store_name}</span>
                  <div className="product-price"><strong>{new Intl.NumberFormat("id-ID", { style: "currency", currency: product.currency, maximumFractionDigits: product.currency === "IDR" ? 0 : 2 }).format(product.price)}</strong></div>
                  <div className="product-meta">
                    {typeof product.rating === "number" && <span>★ {product.rating}</span>}
                    {typeof product.review_count === "number" && <span>{product.review_count.toLocaleString("id-ID")} ulasan</span>}
                  </div>
                  <div className="recommendation-scores"><span>Trust {recommendation.trust_score}/100</span><span>Kecocokan {recommendation.match_score}/100</span></div>
                  <details className="recommendation-reasons">
                    <summary>Mengapa direkomendasikan?</summary>
                    <p>{recommendation.why_recommended}</p>
                    {recommendation.pros.length > 0 && <><h4>Kelebihan</h4><ul>{recommendation.pros.map((pro, index) => <li key={index}>{pro}</li>)}</ul></>}
                    {recommendation.cons.length > 0 && <><h4>Pertimbangan</h4><ul>{recommendation.cons.map((con, index) => <li key={index}>{con}</li>)}</ul></>}
                  </details>
                  {storeUrl ? <a className="store-link" href={storeUrl} target="_blank" rel="noopener noreferrer">Lihat di toko <Icon name="chevron" size={15} /></a> : <p className="store-unavailable">Tautan toko belum tersedia</p>}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="search" size={30} /><h3>{response ? "Belum ada rekomendasi yang sesuai" : "Mulai dari produk yang Anda cari"}</h3>
          <p>{response ? "Coba kata kunci yang lebih spesifik atau ubah rentang harga, lalu cari lagi." : "Masukkan kata kunci, atur budget jika perlu, lalu tekan Cari."}</p>
          {response && <button type="button" onClick={onReset}>Reset pencarian</button>}
        </div>
      )}
    </section>
  );
}
