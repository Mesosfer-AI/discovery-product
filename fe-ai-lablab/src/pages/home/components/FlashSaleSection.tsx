import Icon from "../../../components/ui/Icon";
import { formatRupiah, products } from "../data";

export default function FlashSaleSection() {
  return (
    <section className="page-width section-card flash-section">
      <div className="flash-heading">
        <div className="flash-title"><span>INSPIRASI</span><strong>CONTOH PRODUK</strong></div>
        <div className="timer"><Icon name="clock" size={16} /><span>Berakhir dalam</span><b>08</b><i>:</i><b>24</b><i>:</i><b>16</b></div>
        <button type="button">Lihat semua <Icon name="chevron" size={15} /></button>
      </div>
      <div className="flash-products">
        {products.slice(0, 6).map((product) => (
          <article className="flash-product" key={product.id}>
            <div className="flash-image">
              <img src={product.image} alt={product.name} />
              <span>-{product.discount}%</span>
            </div>
            <h3>{product.name}</h3>
            <strong>{formatRupiah(product.price)}</strong>
            <del>{formatRupiah(product.old)}</del>
            <div className="stock-bar"><i style={{ width: `${40 + product.id * 7}%` }} /><span>{product.id % 2 ? "Segera habis" : `${10 + product.id} tersisa`}</span></div>
          </article>
        ))}
      </div>
    </section>
  );
}
