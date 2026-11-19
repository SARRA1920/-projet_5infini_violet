# Module IA — Intelligence & Prédictions

Documentation technique et fonctionnelle du module **IA** de TradeLab
(navigation : *TradeLab / Intelligence → IA & Prédictions*).

Public visé : membres de l'équipe qui utilisent, maintiennent ou étendent le
module, et enseignants qui évaluent les choix de modélisation.

---

## Sommaire

1. [Présentation](#1-présentation)
2. [Architecture](#2-architecture)
3. [Prédiction de cours](#3-prédiction-de-cours)
4. [Agent de trading](#4-agent-de-trading)
5. [Backtest walk-forward (sans fuite de données)](#5-backtest-walk-forward-sans-fuite-de-données)
6. [Sentiment multilingue FR/EN](#6-sentiment-multilingue-fren)
7. [Filtrage des actualités par actif](#7-filtrage-des-actualités-par-actif)
8. [Référence de l'API](#8-référence-de-lapi)
9. [Tests](#9-tests)
10. [Limites connues et évolutions](#10-limites-connues-et-évolutions)

---

## 1. Présentation

Le module couvre la section 3.4 du cahier des charges : prédiction de
marchés, agent intelligent de trading et analyse de sentiments. Trois
briques indépendantes, combinées par l'agent :

| Brique | Fichier | Modèle |
|---|---|---|
| Prédiction de cours | `backend/app/ia/prediction.py` | RandomForestRegressor (scikit-learn) |
| Features techniques | `backend/app/ia/features.py` | fonctions pures numpy (RSI, SMA, volatilité, momentum) |
| Agent de trading | `backend/app/ia/agent.py` | policy rule-based, score composite explicable |
| Sentiment | `backend/app/ia/sentiment.py` | lexique financier FR / VADER (EN) |
| Backtest | `backend/app/ia/agent.py` | walk-forward, coûts et contraintes réels |

**Conventions** : rendements en fractions (0.023 = 2,3 %), 252 jours de
bourse par an, erreurs explicites (`ValueError`) plutôt que résultats
trompeurs quand l'historique est insuffisant.

## 2. Architecture

```
backend/app/ia/
  features.py     # features techniques (aucun accès BD, numpy pur)
  prediction.py   # entraînement + inférence + cache mémoire (TTL 10 min)
  sentiment.py    # sentiment FR/EN + récupération et filtrage des news
  agent.py        # agent (décision explicable) + backtest walk-forward
  schemas.py      # modèles Pydantic des réponses
  api.py          # routes FastAPI sous /api/ia (JWT requis)
frontend/src/pages/ia/
  IaDashboard.jsx    # état du module (sklearn, vader, cache)
  PredictionPage.jsx # prédiction + jauge de confiance + importance des features
  AgentPage.jsx      # décision + raisons contributives
  SentimentPage.jsx  # analyse de texte libre + sentiment par actif
  BacktestPage.jsx   # backtest walk-forward + équité vs buy & hold
```

Nouvelles dépendances (`backend/requirements.txt`) : `scikit-learn`,
`pandas`, `joblib`, `vaderSentiment`.

## 3. Prédiction de cours

- **Features** (12) : `ret_1/5/10`, ratios prix/SMA20 et prix/SMA50,
  `rsi_14` (Wilder), `vol_20`, `momentum_10`, `volume_ratio_20`, plus les
  features « visibles de la baisse » ajoutées en v3 : `drawdown_20`
  (distance au plus haut des 20 derniers jours, ≤ 0), `sma20_slope`
  (pente de la SMA20 sur 5 jours) et `bb_pos` (position dans les bandes de
  Bollinger, 0 par convention si σ = 0). Sans elles, le RandomForest ne
  « voyait » jamais qu'il était en pleine chute.
- **Cible** : rendement cumulé sur `horizon` jours (1 à 30).
- **Modèle** : RandomForest (200 arbres, profondeur 8, `random_state=42`)
  entraîné à la demande sur `price_history`, mis en cache par
  `symbol:horizon` (TTL 10 min). Minimum **120 points** d'historique (relevé
  de 60 : deux régimes de marché minimum) et 20 échantillons.
- **Incertitude** : quantiles 10–90 % des prédictions individuelles des
  arbres → intervalle de confiance ; score de confiance = dispersion
  inversée.
- **Explicabilité** : `GET /feature-importance/{symbol}` renvoie les
  importances normalisées du RandomForest (XAI global, section 3.6 du
  cahier des charges).
- **Diagnostic** : `GET /diagnostics/{symbol}` répond à la question « pourquoi
  le modèle prédit-il (presque) toujours du positif ? » — IC de Spearman par
  feature (une importance élevée avec un IC ≈ 0 = mémorisation, pas de
  généralisation), part de prédictions positives vs part de cibles positives
  (biais de signe, cause racine : moyenne de la cible positive sur un titre
  montant), et calibration par quintile de prédiction (le classement peut
  être informatif même avec un biais de niveau).

## 4. Agent de trading

Score composite dans [-1, +1] :

```
composite = 0.5 × prédiction normalisée par la volatilité
          + 0.3 × technique (RSI 30/70 ±0.4, SMA20/SMA50 ±0.3)
          + 0.2 × sentiment agrégé (titres filtrés)
```

`|composite| > 0.25` → BUY ou SELL, sinon HOLD. Le seuil, relevé de 0.15 à
0.25 (v3), exige un consensus plus net des signaux. Par-dessus le score, un
**filtre de tendance** bloque tout BUY quand SMA20 < SMA50 (tendance
baissière confirmée — le scénario des jours 128–134 où l'ancien agent
achetait pendant une chute de 7,8 %) et tout SELL en tendance haussière ; la
décision est ramenée à HOLD avec une raison explicite (signal « filtre »,
confiance plafonnée à 0.5). Chaque décision expose son **seuil** et ses
**raisons** (signal, détail lisible, contribution signée) : l'utilisateur
peut auditer pourquoi l'agent dit BUY — exigence « les décisions de l'agent
devront pouvoir être analysées » du cahier des charges. Le RL est écarté
volontairement (données insuffisantes, moins explicable) ; `decide()`
pourrait être remplacé sans changer l'interface.

## 5. Backtest walk-forward (sans fuite de données)

La première version entraînait le modèle sur **tout** l'historique puis
l'évaluait sur **ces mêmes jours** : le taux de réussite affiché (~95 %)
était une mémorisation, pas une prédiction. La version corrigée :

1. **Validation walk-forward** : au jour t, le modèle n'est entraîné que
   sur les échantillons `s` dont la cible est réalisée **avant** t
   (`s + horizon ≤ t`). Garantie vérifiable sur chaque trade renvoyé :
   `train_last_index + horizon ≤ index`.
2. **Réentraînement périodique** (`retrain_every`, 5 jours par défaut) :
   fenêtre glissante, coûts de calcul maîtrisés.
3. **Imputation sans fuite** : les moyennes d'imputation des NaN sont
   calculées sur la fenêtre d'entraînement uniquement.

**Réalisme de l'exécution** :

- frais de transaction + slippage (`fee_bps` + `slippage_bps` par côté,
  10 + 5 bps par défaut) ;
- chaque position engage `capital_fraction` de l'équité (25 % par défaut)
  et **bloque** ce capital `horizon` jours ; au plus
  `1 / capital_fraction` positions simultanées, sinon le signal est
  ignoré (`n_skipped`) ;
- **vente à découvert interdite** par défaut (`allow_short=False`),
  cohérent avec la règle plateforme — un signal SELL reste en cash
  (`n_flat`) ;
- métriques honnêtes : rendement **net** de la stratégie, benchmark
  **buy & hold** sur la même fenêtre, courbes d'équité mark-to-market,
  drawdown maximal, **IC** (corrélation de Spearman prédit/réel),
  win rate hors échantillon.

Sur données identiques, la correction transforme typiquement un
« 90 % de réussite, +200 % » illusoire en ~55–65 % de réussite hors
échantillon et un rendement net comparable au buy & hold — c'est le
résultat vrai, et l'IC (souvent 0,1–0,3) montre un pouvoir prédictif
réel mais modeste, comme attendu sur des cours journaliers.

## 6. Sentiment multilingue FR/EN

VADER ne comprend pas le français (score 0.0 sur « Apple annonce des
bénéfices record ») et son lexique généraliste ignore « beats »,
« misses »… Le module route donc par langue :

- **détection** : mots-outils FR/EN, puis couverture lexicale en cas
  d'égalité ; comparaison insensible aux accents ;
- **FR** : lexique financier maison (~150 termes haussiers/baissiers)
  avec **négation** (« ne … pas », « sans », « aucun », rayon de 3
  tokens, valence inversée ×0.8), **intensifiants** (« très »,
  « fortement » — l'adverbe français suit le verbe, l'adjectif précède
  le nom : les deux positions sont examinées) et **atténuants**
  (« légèrement », ×0.5) ;
- **EN** : VADER s'il est disponible ; si VADER renvoie 0.0 alors que le
  lexique financier EN reconnaît des mots, le lexique financier prime.

Évolution prévue : FinBERT multilingue (`transformers` + `torch`,
~420 Mo) — l'interface `analyze_sentiment` resterait identique.

## 7. Filtrage des actualités par actif

Le flux RSS Yahoo d'un ticker mélange des actualités génériques
(SpaceX, Walmart…) qui polluaient le score. `fetch_headlines(symbol,
company_name)` :

1. récupère jusqu'à 30 titres (Yahoo RSS, repli Google News — la
   requête Google inclut le nom de l'entreprise) ;
2. construit les **alias** : ticker + mots significatifs du nom
   d'entreprise (les mots génériques « Inc », « group », « year »… sont
   exclus) ;
3. ne conserve qu'un titre mentionnant un alias (frontière de mot,
   pluriel accepté, accents ignorés) et déduplique.

Sans alias exploitable, le filtrage est désactivé (mieux vaut un score
bruité qu'un score vide). Erreurs réseau absorbées → liste vide, le
sentiment ne contribue alors pas au score de l'agent.

## 8. Référence de l'API

Toutes les routes exigent un JWT (utilisateur connecté).

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/ia/status` | dépendances disponibles, modèles en cache |
| GET | `/api/ia/predict/{symbol}?horizon=5` | prédiction + intervalle + confiance |
| GET | `/api/ia/feature-importance/{symbol}` | importances du RandomForest |
| GET | `/api/ia/sentiment/{symbol}` | sentiment agrégé des titres **filtrés** |
| POST | `/api/ia/sentiment/analyze` | sentiment d'un texte libre (FR/EN) |
| GET | `/api/ia/agent/{symbol}?horizon=5` | décision + raisons explicables |
| GET | `/api/ia/backtest/{symbol}` | backtest walk-forward (voir paramètres) |
| POST | `/api/ia/retrain/{symbol}?horizon=5` | réentraînement forcé |

Paramètres du backtest (query) : `horizon` (1–30), `capital_fraction`
(0.05–1.0), `fee_bps` (0–100), `slippage_bps` (0–100), `retrain_every`
(1–60), `allow_short` (défaut false), `max_points` (10–500). Réponse :
métriques de réussite et de rendement net, `buy_hold_return`,
`max_drawdown`, `information_coefficient`, `fees_paid`, `n_opened`,
`n_skipped`, `n_flat`, `equity_curve` (stratégie vs buy & hold) et le
journal des décisions (`train_size`, `train_last_index`, `opened`,
`pnl`).

## 9. Tests

`backend/tests/` :

- `test_ia_features.py` — fonctions de features (15 tests) ;
- `test_ia_prediction.py` — pipeline prédiction (6) ;
- `test_ia_improvements.py` — importance des features + backtest (6) ;
- `test_ia_sentiment_fr.py` — français, négation, intensifiants,
  filtrage des titres (23) ;
- `test_ia_backtest_walkforward.py` — **preuves d'absence de fuite**
  (`train_last_index + horizon ≤ index`), réalisme (frais, slots,
  no-short), métriques honnêtes, déterminisme (18) ;
- `test_ia_api.py` — intégration HTTP des routes modifiées (6).

Exécution : `docker compose exec backend pytest tests/test_ia_* -v`.

## 10. Limites connues et évolutions

- Le backtest n'intègre pas le sentiment (pas d'historique de news
  archivé) ; le score composite y vaut 0.5·prédiction + 0.3·technique.
- Les modèles vivent en mémoire par processus (pas de partage entre
  workers uvicorn, perte au redémarrage) : assumé pour l'échelle du
  projet ; `joblib` est disponible si une persistance devient utile.
- Un jour de décision sans assez de passé (`< min_train_samples`) n'est
  pas évalué : `n_points` est donc plus petit que l'historique.
- Évolutions naturelles : FinBERT pour le sentiment, recommandations au
  niveau portefeuille (pas seulement par actif), détection d'anomalies,
  et connexion décision → passage d'ordre papier dans le module trading.
