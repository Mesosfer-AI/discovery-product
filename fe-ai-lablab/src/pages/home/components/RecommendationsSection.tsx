
import Icon from "../../../components/ui/Icon";
import {
  safeExternalUrl,
  type DiscoveryResponse,
  type Recommendation,
} from "../../../features/discovery/api";
import PriceRangeFilter from "./PriceRangeFilter";

type RecommendationsSectionProps = {
  query: string;
  recommendations: Recommendation[];
  searchedQuery: string;
  isLoading: boolean;
  error: string;
  response: DiscoveryResponse | null;
  favorites: string[];
  minPrice: number | "";
  maxPrice: number | "";
  onQueryChange: (query: string) => void;
  onFavoriteToggle: (id: string) => void;
  onSearch: () => void;
  onMinPriceChange: (value: number | "") => void;
  onMaxPriceChange: (value: number | "") => void;
  onClearPrice: () => void;
  onReset: () => void;
};

export default function RecommendationsSection({
  query,
  recommendations,
  searchedQuery,
  isLoading,
  error,
  response,
  favorites,
  minPrice,
  maxPrice,
  onQueryChange,
  onFavoriteToggle,
  onSearch,
  onMinPriceChange,
  onMaxPriceChange,
  onClearPrice,
  onReset,
}: RecommendationsSectionProps) {
  return (
    <section
      className="page-width catalog-layout"
      id="rekomendasi"
      aria-label="Rekomendasi produk"
      aria-busy={isLoading}
    >
      <aside className="catalog-sidebar">
        <div className="catalog-sidebar__intro">
          <span>Belanja di EKLEGORIA</span>
          <h1>Cari produk pilihanmu</h1>
          <p>
            Temukan produk lokal terbaik yang sesuai dengan
            kebutuhan dan budget kamu.
          </p>
        </div>

        <form
          className="catalog-search"
          role="search"
          onSubmit={(event) => {
            event.preventDefault();
            onSearch();
          }}
        >
          <Icon name="search" size={18} />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Cari produk atau toko"
            aria-label="Cari produk atau toko"
            minLength={2}
            required
          />
          <button
            type="submit"
            disabled={isLoading || query.trim().length < 2}
          >
            {isLoading ? "…" : "Cari"}
          </button>
        </form>

        <div className="catalog-filter">
          <div className="catalog-filter__heading">
            <div>
              <span>Filter produk</span>
              <strong>Sesuaikan pencarian</strong>
            </div>

            {(query || minPrice !== "" || maxPrice !== "" || error) && (
              <button
                type="button"
                onClick={onReset}
                disabled={isLoading}
              >
                Reset
              </button>
            )}
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
        </div>
      </aside>

      <div className="catalog-results">
        <div className="catalog-results__heading">
          <div>
            <span>Koleksi EKLEGORIA</span>
            <h2>
              {searchedQuery
                ? `Hasil untuk "${searchedQuery}"`
                : "Produk pilihan untukmu"}
            </h2>
          </div>

          <p>
            <strong>{isLoading ? "…" : recommendations.length}</strong>{" "}
            rekomendasi
          </p>
        </div>

        {response && !isLoading && !error && (
          <p className="discovery-summary">
            {response.total_discovered} kandidat ditemukan
            {" · "}
            {response.execution_time_seconds.toFixed(1)} detik
          </p>
        )}

        {isLoading ? (
          <div className="empty-state" role="status" aria-live="polite">
            <Icon name="search" size={30} />
            <h3>Sedang mencari rekomendasi…</h3>
            <p>
              Kami sedang mencari produk dan menilai kecocokannya.
              Proses ini dapat memerlukan beberapa menit.
            </p>
          </div>
        ) : error ? (
          <div className="empty-state" role="alert">
            <h3>Pencarian belum berhasil</h3>
            <p>{error}</p>
            <button
              type="button"
              onClick={onSearch}
              disabled={query.trim().length < 2}
            >
              Coba lagi
            </button>
          </div>
        ) : recommendations.length > 0 ? (
          <div className="product-grid">
            {recommendations.map((recommendation) => {
              const { product } = recommendation;
              const favorite = favorites.includes(product.id);
              const storeUrl = safeExternalUrl(product.url);
              const imageUrl = safeExternalUrl(product.image_url);

              return (
                <a
                  key={product.id}
                  className={`product-card discovery-card${storeUrl ? " clickable-card" : ""}`}
                  href={storeUrl ?? undefined}
                  target={storeUrl ? "_blank" : undefined}
                  rel={storeUrl ? "noopener noreferrer" : undefined}
                  aria-label={`Lihat ${product.title} di toko`}
                  style={{ textDecoration: "none", color: "inherit", display: "block" }}
                >
                  <article>
                    <div className="product-image">
                      {imageUrl ? (
                        <img
                          src={imageUrl}
                          alt={product.title}
                          loading="lazy"
                        />
                      ) : (
                        <div className="product-image-placeholder">
                          <Icon name="store" size={30} />
                          <span>Gambar belum tersedia</span>
                        </div>
                      )}

                      <span className="product-label">
                        Pilihan #{recommendation.rank}
                      </span>

                      <button
                        type="button"
                        className={`favorite ${favorite ? "active" : ""}`}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          onFavoriteToggle(product.id);
                        }}
                        aria-pressed={favorite}
                        aria-label={
                          favorite
                            ? "Hapus dari favorit"
                            : "Tambah ke favorit"
                        }
                      >
                        <Icon name="heart" size={17} fill={favorite} />
                      </button>
                    </div>

                    <div className="product-info">
                      <h3>{product.title}</h3>

                      <span className="shop">
                        <Icon name="store" size={12} />
                        {" "}{product.store_name}
                      </span>

                      <div className="product-price">
                        <strong>
                          {new Intl.NumberFormat("id-ID", {
                            style: "currency",
                            currency: product.currency,
                            maximumFractionDigits:
                              product.currency === "IDR" ? 0 : 2,
                          }).format(product.price)}
                        </strong>
                      </div>

                      <div className="product-meta">
                        {typeof product.rating === "number" && (
                          <span>★ {product.rating}</span>
                        )}
                        {typeof product.review_count === "number" && (
                          <span>
                            {product.review_count.toLocaleString("id-ID")} ulasan
                          </span>
                        )}
                      </div>

                      <div className="recommendation-scores">
                        <span>
                          Trust {recommendation.trust_score}/100
                        </span>
                        <span>
                          Kecocokan {recommendation.match_score}/100
                        </span>
                      </div>

                      <details
                        className="recommendation-reasons"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <summary>Mengapa direkomendasikan?</summary>
                        <p>{recommendation.why_recommended}</p>

                        {recommendation.pros.length > 0 && (
                          <>
                            <h4>Kelebihan</h4>
                            <ul>
                              {recommendation.pros.map((pro, index) => (
                                <li key={index}>{pro}</li>
                              ))}
                            </ul>
                          </>
                        )}

                        {recommendation.cons.length > 0 && (
                          <>
                            <h4>Pertimbangan</h4>
                            <ul>
                              {recommendation.cons.map((con, index) => (
                                <li key={index}>{con}</li>
                              ))}
                            </ul>
                          </>
                        )}
                      </details>

                      {storeUrl ? (
                        <span className="store-link" aria-hidden="true">
                          Lihat di toko
                          <Icon name="chevron" size={12} />
                        </span>
                      ) : (
                        <span className="store-unavailable">
                          Tautan toko belum tersedia
                        </span>
                      )}
                    </div>
                  </article>
                </a>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">
            <h3>
              {response
                ? "Belum ada rekomendasi yang sesuai"
                : "Mulai dari produk yang kamu cari"}
            </h3>
            <p>
              {response
                ? "Coba kata kunci yang lebih spesifik atau ubah rentang harga, lalu cari lagi."
                : "Masukkan kata kunci, atur budget jika perlu, lalu tekan Cari."}
            </p>

            {response && (
              <button type="button" onClick={onReset}>
                Reset pencarian
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
