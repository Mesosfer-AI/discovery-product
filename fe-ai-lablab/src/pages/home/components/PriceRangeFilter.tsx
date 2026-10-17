
type PriceRangeFilterProps = {
  minPrice: number | "";
  maxPrice: number | "";
  onMinPriceChange: (value: number | "") => void;
  onMaxPriceChange: (value: number | "") => void;
  onClear: () => void;
  onApply: () => void;
  isLoading: boolean;
};

const presets = [
  { label: "Di bawah Rp150rb", min: "", max: 150000 },
  { label: "Rp150rb – Rp300rb", min: 150000, max: 300000 },
  { label: "Rp300rb – Rp500rb", min: 300000, max: 500000 },
  { label: "Di atas Rp500rb", min: 500000, max: "" },
] as const;

export default function PriceRangeFilter({
  minPrice,
  maxPrice,
  onMinPriceChange,
  onMaxPriceChange,
  onClear,
  onApply,
  isLoading,
}: PriceRangeFilterProps) {
  const updatePrice = (
    rawValue: string,
    onChange: (value: number | "") => void,
  ) => {
    onChange(rawValue === "" ? "" : Math.max(0, Number(rawValue)));
  };

  const activePreset = (min: number | "", max: number | "") =>
    minPrice === min && maxPrice === max;

  return (
    <div className="price-filter">
      <div className="price-filter__label">
        <strong>Rentang harga</strong>
        <span>Pilih sesuai budget kamu</span>
      </div>

      <div className="price-inputs">
        <label>
          <span>Rp</span>
          <input
            type="number"
            min="0"
            step="10000"
            value={minPrice}
            onChange={(event) =>
              updatePrice(event.target.value, onMinPriceChange)
            }
            placeholder="Minimum"
            aria-label="Harga minimum"
          />
        </label>

        <i>—</i>

        <label>
          <span>Rp</span>
          <input
            type="number"
            min="0"
            step="10000"
            value={maxPrice}
            onChange={(event) =>
              updatePrice(event.target.value, onMaxPriceChange)
            }
            placeholder="Maksimum"
            aria-label="Harga maksimum"
          />
        </label>
      </div>

      <div className="price-presets">
        {presets.map((preset) => (
          <button
            type="button"
            key={preset.label}
            className={
              activePreset(preset.min, preset.max) ? "active" : ""
            }
            onClick={() => {
              onMinPriceChange(preset.min);
              onMaxPriceChange(preset.max);
            }}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {(minPrice !== "" || maxPrice !== "") && (
        <button
          type="button"
          className="clear-price"
          onClick={onClear}
        >
          Hapus filter harga
        </button>
      )}
    </div>
  );
}
