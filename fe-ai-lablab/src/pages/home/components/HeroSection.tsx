import Icon from "../../../components/ui/Icon";

export default function HeroSection() {
  return (
    <>
      <section className="page-width hero-grid">
        <div className="main-banner">
          <div className="banner-copy">
            <span className="promo-kicker">LOKA MID MONTH</span>
            <h1>Belanja bagus,<br />harga nggak bikin ragu.</h1>
            <p>Diskon sampai 50% + gratis ongkir tanpa minimum belanja.</p>
            <button type="button" onClick={() => document.getElementById("rekomendasi")?.scrollIntoView({ behavior: "smooth" })}>
              Belanja sekarang <Icon name="chevron" size={16} />
            </button>
          </div>
          <div className="banner-image">
            <span className="circle-deco circle-one" />
            <span className="circle-deco circle-two" />
            <img src="https://images.unsplash.com/photo-1735992006502-3d7c73dfc895?auto=format&fit=crop&w=900&q=88" alt="Koleksi fashion pilihan Loka" />
            <div className="discount-sticker"><small>hingga</small><strong>50%</strong><span>OFF</span></div>
          </div>
          <div className="banner-dots"><i /><i /><i /></div>
        </div>

        <div className="side-promos">
          <article className="side-card voucher-card">
            <div><span>KHUSUS PENGGUNA BARU</span><h2>Voucher<br /><strong>Rp50RB</strong></h2><button type="button">Klaim sekarang</button></div>
            <span className="voucher-shape"><Icon name="tag" size={30} /></span>
          </article>
          <article className="side-card shipping-card">
            <div><span>SETIAP HARI</span><h2>Gratis Ongkir</h2><p>Min. belanja Rp0</p></div>
            <span className="truck-shape"><Icon name="truck" size={40} /></span>
          </article>
        </div>
      </section>

      <section className="page-width benefit-row" aria-label="Keunggulan Loka">
        <div><span><Icon name="truck" size={21} /></span><p><strong>Gratis Ongkir</strong><small>Ke seluruh Indonesia</small></p></div>
        <div><span><Icon name="shield" size={21} /></span><p><strong>Belanja Aman</strong><small>Garansi uang kembali</small></p></div>
        <div><span><Icon name="tag" size={21} /></span><p><strong>Harga Terbaik</strong><small>Promo setiap hari</small></p></div>
        <div><span><Icon name="store" size={21} /></span><p><strong>Produk Lokal</strong><small>Dari seller terpercaya</small></p></div>
      </section>
    </>
  );
}
