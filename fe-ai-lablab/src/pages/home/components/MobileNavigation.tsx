import Icon from "../../../components/ui/Icon";
import type { AuthMode } from "../../../features/auth/AuthModal";

type MobileNavigationProps = {
  cartCount: number;
  isLoggedIn: boolean;
  onOpenAuth: (mode: AuthMode) => void;
};

export default function MobileNavigation({ cartCount, isLoggedIn, onOpenAuth }: MobileNavigationProps) {
  return (
    <nav className="mobile-nav" aria-label="Navigasi utama">
      <button type="button" className="active"><Icon name="home" size={21} /><span>Beranda</span></button>
      <button type="button"><Icon name="grid" size={21} /><span>Kategori</span></button>
      <button type="button" className="nav-cart"><Icon name="cart" size={21} /><b>{cartCount}</b><span>Keranjang</span></button>
      <button type="button"><Icon name="heart" size={21} /><span>Favorit</span></button>
      <button type="button" onClick={() => !isLoggedIn && onOpenAuth("login")}><Icon name="user" size={21} /><span>{isLoggedIn ? "Nadia" : "Akun"}</span></button>
    </nav>
  );
}
