// Chiffres de la maquette TradeLab. Ils seront remplacés par les vraies cotations
// et le portefeuille quand ces modules seront branchés.

export const quotes = [
  {
    symbol: "SFBT",
    name: "Société Frigorifique",
    last: "13 240 TND",
    change: "+1,85 %",
    high: "13 380",
    low: "12 840",
    volume: "48,7K",
    up: true,
    group: "actions",
    spark: [20, 18, 17, 14, 13, 10, 8],
  },
  {
    symbol: "BIAT",
    name: "Banque Internationale Arabe",
    last: "105 500 TND",
    change: "+0,72 %",
    high: "106 200",
    low: "104 810",
    volume: "12,8K",
    up: true,
    group: "actions",
    spark: [22, 19, 18, 16, 14, 12, 9],
  },
  {
    symbol: "AAPL",
    name: "Apple Inc.",
    last: "227,16 USD",
    change: "+1,20 %",
    high: "229,04",
    low: "223,02",
    volume: "31,4M",
    up: true,
    group: "actions",
    spark: [18, 17, 15, 14, 12, 11, 8],
  },
  {
    symbol: "TSLA",
    name: "Tesla Inc.",
    last: "248,98 USD",
    change: "-2,14 %",
    high: "255,18",
    low: "245,44",
    volume: "84,1M",
    up: false,
    group: "actions",
    spark: [8, 10, 11, 14, 16, 19, 22],
  },
  {
    symbol: "EUR/USD",
    name: "Euro / Dollar US",
    last: "1,0842",
    change: "+0,42 %",
    high: "1,0864",
    low: "1,0798",
    volume: "—",
    up: true,
    group: "devises",
    spark: [18, 16, 15, 13, 12, 10, 8],
  },
  {
    symbol: "XAU/USD",
    name: "Or / USD",
    last: "2 658,40 USD",
    change: "-0,31 %",
    high: "2 674,10",
    low: "2 641,70",
    volume: "—",
    up: false,
    group: "matieres",
    spark: [9, 11, 12, 14, 16, 18, 21],
  },
];

export const filters = [
  { id: "tous", label: "Tous" },
  { id: "actions", label: "Actions" },
  { id: "devises", label: "Devises" },
  { id: "matieres", label: "Matières premières" },
];

export const allocation = [
  { label: "Actions tunisiennes", value: 36, color: "#3dd68c" },
  { label: "Actions internationales", value: 27, color: "#3b82f6" },
  { label: "Devises", value: 18, color: "#a78bfa" },
  { label: "Matières premières", value: 11, color: "#fb923c" },
  { label: "Liquidités", value: 8, color: "#64748b" },
];

export const positions = [
  { symbol: "SFBT", name: "Société Frigorifique", qty: "120", price: "13 240 TND", pnl: "+1,85 %", up: true },
  { symbol: "AAPL", name: "Apple Inc.", qty: "8", price: "227,16 USD", pnl: "+1,20 %", up: true },
  { symbol: "TSLA", name: "Tesla Inc.", qty: "4", price: "248,98 USD", pnl: "-2,14 %", up: false },
  { symbol: "EUR/USD", name: "Euro / Dollar US", qty: "10 000", price: "1,0842", pnl: "+0,42 %", up: true },
];

export const performance = {
  "1J": { label: "+0,42 %", values: [10, 12, 11, 14, 13, 16, 18] },
  "1S": { label: "+2,10 %", values: [8, 10, 9, 13, 12, 15, 14, 18, 20] },
  "1M": { label: "+8,42 %", values: [6, 8, 7, 11, 10, 14, 13, 16, 15, 18, 17, 22] },
  "1A": { label: "+18,40 %", values: [4, 6, 5, 8, 9, 8, 12, 11, 15, 14, 18, 17, 21, 24] },
};
