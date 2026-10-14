export const users = [
  { id: 1, name: "Amine Ben Salah", email: "amine@example.com", role: "user", active: true, joined: "02 oct. 2026", cash: "124 850 TND", pnl: "+8,42 %", orders: 14 },
  { id: 2, name: "Sarra", email: "sarra@example.com", role: "admin", active: true, joined: "28 sep. 2026", cash: "100 000 TND", pnl: "+1,10 %", orders: 2 },
  { id: 3, name: "Test", email: "test@example.com", role: "user", active: true, joined: "10 oct. 2026", cash: "98 400 TND", pnl: "-1,60 %", orders: 6 },
  { id: 4, name: "Admin", email: "admin@example.com", role: "admin", active: true, joined: "28 sep. 2026", cash: "100 000 TND", pnl: "0,00 %", orders: 0 },
  { id: 5, name: "Lina Trabelsi", email: "lina@example.com", role: "user", active: false, joined: "04 oct. 2026", cash: "87 200 TND", pnl: "-4,20 %", orders: 9 },
];

export const assets = [
  { id: 1, symbol: "AAPL", name: "Apple Inc.", type: "Action", source: "Twelve Data", active: true },
  { id: 2, symbol: "EUR/USD", name: "Euro / Dollar", type: "Devise", source: "Twelve Data", active: true },
  { id: 3, symbol: "XAU/USD", name: "Or", type: "Matière première", source: "Twelve Data", active: true },
  { id: 4, symbol: "SFBT", name: "Société Frigorifique", type: "Action", source: "Maquette", active: false },
];

export const news = [
  { id: 1, title: "La Fed maintient ses taux", source: "Reuters", active: true },
  { id: 2, title: "Le pétrole se replie", source: "Bloomberg", active: true },
  { id: 3, title: "Bourse de Tunis : séance calme", source: "Maquette", active: false },
];

export const courses = [
  { id: 1, title: "Lire une cotation", kind: "Cours", status: "Publié" },
  { id: 2, title: "Passer un premier ordre", kind: "Exercice", status: "Publié" },
  { id: 3, title: "Quiz : actions et devises", kind: "Quiz", status: "Brouillon" },
  { id: 4, title: "Défi de la semaine", kind: "Défi", status: "Brouillon" },
];

export const scenarios = [
  { id: 1, name: "Hausse des taux", kind: "Stress", shock: "Taux", intensity: "Fort", status: "Prêt" },
  { id: 2, name: "Krach actions -20 %", kind: "Stress", shock: "Marché", intensity: "Sévère", status: "Prêt" },
  { id: 3, name: "Séance calme", kind: "Marché", shock: "Aucun", intensity: "Faible", status: "Brouillon" },
];

export const models = [
  { id: 1, name: "Prédiction tendance", version: "0.3", metric: "Précision 61 %", status: "Actif" },
  { id: 2, name: "Stress pertes", version: "0.1", metric: "MAE 0,08", status: "Inactif" },
  { id: 3, name: "Sentiment actualités", version: "0.2", metric: "F1 0,54", status: "Brouillon" },
];

export const results = [
  { id: 1, scenario: "Hausse des taux", bank: "Banque Atlas", type: "Conventionnelle", impact: "-6,2 % capital" },
  { id: 2, scenario: "Hausse des taux", bank: "Banque Safa", type: "Non conventionnelle", impact: "-3,1 % capital" },
  { id: 3, scenario: "Krach actions -20 %", bank: "Banque Atlas", type: "Conventionnelle", impact: "-11,4 % capital" },
  { id: 4, scenario: "Krach actions -20 %", bank: "Banque Safa", type: "Non conventionnelle", impact: "-8,0 % capital" },
];

export const audit = [
  { id: 1, who: "Sarra", action: "Changement de rôle", target: "Lina Trabelsi → user", when: "14 oct. 2026 18:12" },
  { id: 2, who: "Admin", action: "Désactivation", target: "Lina Trabelsi", when: "14 oct. 2026 18:20" },
  { id: 3, who: "Sarra", action: "Publication", target: "Cours : Lire une cotation", when: "13 oct. 2026 09:04" },
  { id: 4, who: "Admin", action: "Lancement simulation", target: "Hausse des taux", when: "12 oct. 2026 16:40" },
];

export const usage = [
  { label: "Trading", value: 72 },
  { label: "Marchés", value: 81 },
  { label: "Formation", value: 34 },
  { label: "IA", value: 18 },
  { label: "Stress testing", value: 12 },
];
