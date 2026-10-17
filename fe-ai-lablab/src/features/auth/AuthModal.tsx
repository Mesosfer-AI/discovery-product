import { useState } from "react";
import Icon from "../../components/ui/Icon";

export type AuthMode = "login" | "register";

type AuthModalProps = {
  mode: AuthMode;
  onModeChange: (mode: AuthMode) => void;
  onClose: () => void;
  onSuccess: (mode: AuthMode) => void;
};

export default function AuthModal({ mode, onModeChange, onClose, onSuccess }: AuthModalProps) {
  const [showPassword, setShowPassword] = useState(false);

  const submitAuth = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSuccess(mode);
  };

  return (
    <div className="auth-overlay" role="presentation" onMouseDown={onClose}>
      <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title" onMouseDown={(event) => event.stopPropagation()}>
        <button type="button" className="auth-close" onClick={onClose} aria-label="Tutup">×</button>
        <div className="auth-brand-panel">
          <button type="button" className="auth-logo">EKLEGORIA<span>.</span></button>
          <div className="auth-brand-copy">
            <span>BELANJA LEBIH TENANG</span>
            <h2>Satu akun untuk semua yang kamu suka.</h2>
            <p>Simpan produk favorit, lacak pesanan, dan nikmati promo khusus member.</p>
          </div>
          <div className="auth-benefits">
            <div><Icon name="shield" size={17} /><span><strong>Transaksi aman</strong><small>Data dan pembayaran terlindungi</small></span></div>
            <div><Icon name="tag" size={17} /><span><strong>Promo khusus</strong><small>Voucher baru setiap minggu</small></span></div>
            <div><Icon name="truck" size={17} /><span><strong>Pesanan terpantau</strong><small>Cek status kiriman dengan mudah</small></span></div>
          </div>
        </div>

        <div className="auth-form-panel">
          <div className="auth-heading">
            <span className="mobile-auth-logo">EKLEGORIA.</span>
            <h2 id="auth-title">{mode === "login" ? "Selamat datang kembali" : "Buat akun baru"}</h2>
            <p>{mode === "login" ? "Masuk untuk melanjutkan belanja di EKLEGORIA." : "Daftar gratis, hanya perlu beberapa langkah."}</p>
          </div>

          <div className="auth-switch">
            <button type="button" className={mode === "login" ? "active" : ""} onClick={() => onModeChange("login")}>Masuk</button>
            <button type="button" className={mode === "register" ? "active" : ""} onClick={() => onModeChange("register")}>Daftar</button>
          </div>

          <form onSubmit={submitAuth}>
            {mode === "register" && (
              <label className="auth-field">
                <span>Nama lengkap</span>
                <input type="text" placeholder="Masukkan nama lengkap" required />
              </label>
            )}
            <label className="auth-field">
              <span>Email atau nomor handphone</span>
              <input type="text" placeholder="contoh@email.com" required />
            </label>
            <label className="auth-field">
              <span>Kata sandi</span>
              <div className="password-field">
                <input type={showPassword ? "text" : "password"} placeholder={mode === "register" ? "Minimal 8 karakter" : "Masukkan kata sandi"} minLength={8} required />
                <button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? "Sembunyikan" : "Lihat"}</button>
              </div>
            </label>

            {mode === "login" ? (
              <div className="auth-options">
                <label><input type="checkbox" /> Ingat saya</label>
                <button type="button">Lupa kata sandi?</button>
              </div>
            ) : (
              <label className="terms-check">
                <input type="checkbox" required />
                <span>Saya menyetujui <button type="button">Syarat & Ketentuan</button> serta <button type="button">Kebijakan Privasi</button> EKLEGORIA.</span>
              </label>
            )}

            <button type="submit" className="auth-submit">{mode === "login" ? "Masuk" : "Buat akun"}</button>
          </form>

          <div className="auth-divider"><span>atau lanjut dengan</span></div>
          <div className="social-buttons">
            <button type="button"><b>G</b> Google</button>
            <button type="button"><b className="apple-mark">●</b> Apple</button>
          </div>
          <p className="auth-footer">
            {mode === "login" ? "Belum punya akun?" : "Sudah punya akun?"}
            <button type="button" onClick={() => onModeChange(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "Daftar sekarang" : "Masuk di sini"}
            </button>
          </p>
        </div>
      </section>
    </div>
  );
}
