import { useEffect, useState } from "react";
import Icon from "../../../components/ui/Icon";

interface MidMonthPopupProps {
  onClose: () => void;
}

export default function MidMonthPopup({ onClose }: MidMonthPopupProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setVisible(true), 120);
    return () => window.clearTimeout(t);
  }, []);

  const handleShopNow = () => {
    handleClose();
    window.setTimeout(() => {
      document.getElementById("rekomendasi")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 320);
  };

  const handleClose = () => {
    setVisible(false);
    window.setTimeout(onClose, 300);
  };

  return (
    <div
      className={`midmonth-overlay ${visible ? "midmonth-overlay--visible" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-label="EKLEGORIA Mid Month Promo"
      onClick={(e) => { if (e.target === e.currentTarget) handleClose(); }}
    >
      <div className={`midmonth-modal ${visible ? "midmonth-modal--visible" : ""}`}>

        {/* Left: image column */}
        <div className="midmonth-image-col">
          <span className="midmonth-circle midmonth-circle--a" />
          <span className="midmonth-circle midmonth-circle--b" />
          <img
            src="/images/popup.png"
            alt="Koleksi fashion pilihan EKLEGORIA Mid Month"
          />
        </div>

        {/* Right: copy column */}
        <div className="midmonth-copy-col">
          <h2 className="midmonth-heading">
            Find What You Need.<br />Pay What You Deserve.
          </h2>

          <br />

          <button
            id="midmonth-shop-btn"
            type="button"
            className="midmonth-cta"
            onClick={handleShopNow}
          >
            Belanja sekarang <Icon name="chevron" size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
