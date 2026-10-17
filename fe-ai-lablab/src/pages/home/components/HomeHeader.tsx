
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

export default function HomeHeader({
  query,
  cartCount,
  isLoggedIn,
  isLoading,
  onQueryChange,
  onSearch,
  onOpenAuth,
}: HomeHeaderProps) {
  return (
    <>
      <div className="utility-bar">
        <div className="page-width utility-inner">
          <div className="utility-links">
            <button type="button"></button>
            <button type="button"></button>
            <button type="button"></button>
          </div>

          <div className="utility-links">

            {isLoggedIn ? (
              <button type="button" className="login-link">
                Halo, Nadia
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => onOpenAuth("register")}
                >
                  Daftar
                </button>
                <button
                  type="button"
                  className="login-link"
                  onClick={() => onOpenAuth("login")}
                >
                  Masuk
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <header className="header">
        <div className="page-width header-inner">
          <button
            type="button"
            className="logo"
            aria-label="Beranda EKLEGORIA"
          >
            EKLEGORIA<span>.</span>
          </button>
        </div>
      </header>
    </>
  );
}
