import Icon from "../../../components/ui/Icon";
import type { AuthMode } from "../../../features/auth/AuthModal";

type HomeHeaderProps = {
  query: string;
  cartCount: number;
  isLoggedIn: boolean;
  isLoading: boolean;
  onQueryChange: (query: string) => void;
  onSearch: () => void;
  onOpenAuth: (mode: AuthMode) => void;
};

export default function HomeHeader({ query, cartCount, isLoggedIn, isLoading, onQueryChange, onSearch, onOpenAuth }: HomeHeaderProps) {
  return (
    <>
      <div className="utility-bar">
        <div className="page-width utility-inner">
          <div className="utility-links">
            <button type="button">Seller Centre</button>
            <button type="button">Mulai Berjualan</button>
            <button type="button">Download</button>
          </div>
          <div className="utility-links">
            <button type="button"><Icon name="bell" size={13} /> Notifikasi</button>
            <button type="button">Bantuan</button>
            {isLoggedIn ? (
              <button type="button" className="login-link">Halo, Nadia</button>
            ) : (
              <>
                <button type="button" onClick={() => onOpenAuth("register")}>Daftar</button>
                <button type="button" className="login-link" onClick={() => onOpenAuth("login")}>Masuk</button>
              </>
            )}
          </div>
        </div>
      </div>

      <header className="header">
        <div className="page-width header-inner">
          <button type="button" className="logo" aria-label="Beranda Loka">loka<span>.</span></button>
          <div className="search-area">
            <form className="search-field" role="search" onSubmit={(event) => { event.preventDefault(); onSearch(); }}>
              <Icon name="search" size={18} />
              <input value={query} onChange={(event) => onQueryChange(event.target.value)} placeholder="Cari produk, brand, atau toko" aria-label="Cari produk" minLength={2} required />
              <button type="submit" disabled={isLoading || query.trim().length < 2}>{isLoading ? "Mencari…" : "Cari"}</button>
            </form>
          </div>
          <div className="header-actions">
            <button type="button" className="header-icon" aria-label="Keranjang">
              <Icon name="cart" size={23} /><b>{cartCount}</b>
            </button>
            <button type="button" className="header-icon desktop-only" aria-label="Favorit"><Icon name="heart" size={22} /></button>
            <button type="button" className="account desktop-only" onClick={() => !isLoggedIn && onOpenAuth("login")}>
              <span>{isLoggedIn ? "NA" : <Icon name="user" size={17} />}</span>
              <div><small>{isLoggedIn ? "Halo, Nadia" : "Selamat datang"}</small><strong>{isLoggedIn ? "Akun Saya" : "Masuk / Daftar"}</strong></div>
            </button>
          </div>
        </div>
      </header>
    </>
  );
}
