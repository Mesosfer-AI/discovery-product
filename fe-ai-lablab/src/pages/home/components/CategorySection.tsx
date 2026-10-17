import Icon from "../../../components/ui/Icon";
import { categories } from "../data";

type CategorySectionProps = {
  activeCategory: string;
  onCategoryChange: (category: string) => void;
};

export default function CategorySection({ activeCategory, onCategoryChange }: CategorySectionProps) {
  return (
    <section className="page-width section-card category-section">
      <div className="section-title">
        <h2>Kategori Pilihan</h2><button type="button">Lihat semua <Icon name="chevron" size={15} /></button>
      </div>
      <div className="category-list">
        {categories.map((item) => (
          <button
            type="button"
            key={item.name}
            className={activeCategory === item.name ? "active" : ""}
            onClick={() => onCategoryChange(item.name === "Lihat Semua" ? "Semua" : item.name)}
          >
            <span className={`category-icon ${item.tone}`}>{item.symbol}</span>
            <strong>{item.name}</strong>
          </button>
        ))}
      </div>
    </section>
  );
}
