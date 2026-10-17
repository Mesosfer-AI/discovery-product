export type Product = {
  id: number;
  name: string;
  category: string;
  shop: string;
  city: string;
  price: number;
  old: number;
  rating: string;
  sold: string;
  discount: number;
  image: string;
  label: string;
};

export const categories = [
  { name: "Fashion Wanita", symbol: "♢", tone: "peach" },
  { name: "Fashion Pria", symbol: "◇", tone: "blue" },
  { name: "Kecantikan", symbol: "✦", tone: "pink" },
  { name: "Elektronik", symbol: "▣", tone: "sage" },
  { name: "Rumah Tangga", symbol: "⌂", tone: "sand" },
  { name: "Makanan", symbol: "○", tone: "yellow" },
  { name: "Olahraga", symbol: "◒", tone: "blue" },
  { name: "Aksesori", symbol: "△", tone: "pink" },
  { name: "Hobi", symbol: "＋", tone: "sage" },
  { name: "Lihat Semua", symbol: "•••", tone: "neutral" },
];

export const products: Product[] = [
  { id: 1, name: "Daily Canvas Bag — Natural", category: "Fashion Wanita", shop: "Sora Studio", city: "Bandung", price: 189000, old: 259000, rating: "4.9", sold: "1,2rb", discount: 27, image: "https://images.unsplash.com/photo-1511556820780-d912e42b4980?auto=format&fit=crop&w=700&q=85", label: "Bestseller" },
  { id: 2, name: "Rumi Knit Cardigan Premium", category: "Fashion Wanita", shop: "Eunoia Wear", city: "Jakarta", price: 239000, old: 329000, rating: "4.8", sold: "826", discount: 28, image: "https://images.unsplash.com/photo-1624821437492-c2ef1a333f43?auto=format&fit=crop&w=700&q=85", label: "Mall" },
  { id: 3, name: "Aster Mini Watch Rosegold", category: "Aksesori", shop: "Mono Goods", city: "Surabaya", price: 349000, old: 499000, rating: "4.9", sold: "643", discount: 30, image: "https://images.unsplash.com/photo-1783508923592-26119015ca23?auto=format&fit=crop&w=700&q=85", label: "Pilihan" },
  { id: 4, name: "Noa Sunglasses UV400", category: "Aksesori", shop: "Sunday Club", city: "Bali", price: 129000, old: 179000, rating: "4.7", sold: "2,1rb", discount: 28, image: "https://images.unsplash.com/photo-1691053318576-4bf08315e877?auto=format&fit=crop&w=700&q=85", label: "Bestseller" },
  { id: 5, name: "Kinfolk Wooden Serving Tray", category: "Rumah Tangga", shop: "Kayu Rumah", city: "Yogyakarta", price: 159000, old: 210000, rating: "4.8", sold: "512", discount: 24, image: "https://images.unsplash.com/photo-1589988071674-c4a2004d2336?auto=format&fit=crop&w=700&q=85", label: "Lokal" },
  { id: 6, name: "Mori Camera Pouch Canvas", category: "Hobi", shop: "Mono Goods", city: "Surabaya", price: 219000, old: 289000, rating: "4.9", sold: "347", discount: 25, image: "https://images.unsplash.com/photo-1625753732305-eb8b9d1b9f4c?auto=format&fit=crop&w=700&q=85", label: "Baru" },
  { id: 7, name: "Minimalist Ceramic Vase Set", category: "Rumah Tangga", shop: "Ruang Rupa", city: "Malang", price: 179000, old: 235000, rating: "4.8", sold: "734", discount: 24, image: "https://images.unsplash.com/photo-1580679006112-9753b5910fa0?auto=format&fit=crop&w=700&q=85", label: "Pilihan" },
  { id: 8, name: "Lumi Everyday Sneakers", category: "Fashion Wanita", shop: "Langkah Kaki", city: "Bandung", price: 289000, old: 389000, rating: "4.9", sold: "1,8rb", discount: 26, image: "https://images.unsplash.com/photo-1511556820780-d912e42b4980?auto=format&fit=crop&w=700&q=85", label: "Gratis Ongkir" },
  { id: 9, name: "Classic Lens Organizer", category: "Elektronik", shop: "Optik Lab", city: "Jakarta", price: 199000, old: 275000, rating: "4.7", sold: "289", discount: 28, image: "https://images.unsplash.com/photo-1625753732305-eb8b9d1b9f4c?auto=format&fit=crop&w=700&q=85", label: "Baru" },
  { id: 10, name: "Soft Knit Home Blanket", category: "Rumah Tangga", shop: "Ruang Rupa", city: "Malang", price: 269000, old: 349000, rating: "4.9", sold: "930", discount: 23, image: "https://images.unsplash.com/photo-1691053318576-4bf08315e877?auto=format&fit=crop&w=700&q=85", label: "Mall" },
];

export const formatRupiah = (value: number) =>
  `Rp${new Intl.NumberFormat("id-ID").format(value)}`;
