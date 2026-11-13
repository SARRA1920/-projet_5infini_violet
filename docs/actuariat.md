# Module Actuariat — Actuarial & Quantitative Risk Analytics

Documentation technique et fonctionnelle du module **Actuariat** de TradeLab
(navigation : *TradeLab / Intelligence → Actuariat*).

Public visé : membres de l'équipe qui utilisent, maintiennent ou étendent le module,
et enseignants qui évaluent les choix de modélisation.

---

## Sommaire

1. [Présentation](#1-présentation)
2. [Installation et lancement](#2-installation-et-lancement)
3. [Architecture](#3-architecture)
4. [Conventions communes](#4-conventions-communes)
5. [Sous-modules](#5-sous-modules)
   - 5.1 [Tableau de bord actuariel](#51-tableau-de-bord-actuariel)
   - 5.2 [Risk Analytics](#52-risk-analytics)
   - 5.3 [Modèles stochastiques](#53-modèles-stochastiques)
   - 5.4 [Fixed Income Analytics](#54-fixed-income-analytics)
   - 5.5 [Optimisation de portefeuille](#55-optimisation-de-portefeuille)
   - 5.6 [Modèles de pertes et capital économique](#56-modèles-de-pertes-et-capital-économique)
   - 5.7 [Laboratoire de modèles](#57-laboratoire-de-modèles)
6. [Référence de l'API](#6-référence-de-lapi)
7. [Base de données](#7-base-de-données)
8. [Frontend](#8-frontend)
9. [Tests](#9-tests)
10. [Sécurité et isolation des utilisateurs](#10-sécurité-et-isolation-des-utilisateurs)
11. [Performances et limites de calcul](#11-performances-et-limites-de-calcul)
12. [Limites connues et points d'attention](#12-limites-connues-et-points-dattention)
13. [Étendre le module](#13-étendre-le-module)
14. [Reste à faire](#14-reste-à-faire)
15. [Glossaire](#15-glossaire)

---

## 1. Présentation

### 1.1 Objectif

Le module transforme la section Actuariat en environnement de modélisation
quantitative appliqué aux marchés financiers du simulateur :

| Besoin | Sous-module |
|---|---|
| Suivre le risque de son portefeuille | Tableau de bord |
| Calculer VaR et Expected Shortfall par trois méthodes | Risk Analytics |
| Simuler prix et taux d'intérêt | Modèles stochastiques |
| Analyser une obligation (YTM, duration, convexité) | Fixed Income |
| Construire une allocation efficiente | Optimisation |
| Modéliser des distributions de pertes et un capital | Modèles de pertes |
| Comparer les modèles entre eux | Laboratoire |

### 1.2 Périmètre

- **Aucune intelligence artificielle, aucun Machine Learning, aucun Deep Learning.**
  Tous les modèles sont des modèles statistiques et stochastiques classiques, à
  formule explicite.
- **Aucune exécution d'ordre.** Le module lit les portefeuilles et les transactions ;
  il ne passe jamais d'ordre, même après une optimisation (vérifié par un test).
- **Extension incrémentale.** Le module ajoute des fichiers, des routes et deux
  tables. Il ne modifie ni l'authentification, ni le trading, ni les portefeuilles,
  ni l'import Twelve Data, ni les migrations existantes.

### 1.3 Provenance des données

Chaque résultat affiché porte un badge de provenance. C'est une règle du module :
une donnée fictive n'est jamais présentée comme un résultat réel.

| Badge | Valeur API (`data_source`) | Signification |
|---|---|---|
| Données de marché réelles | `real_market_data` | Cours importés de Twelve Data (`price_history`) et positions réelles du simulateur |
| Données synthétiques | `synthetic` | Données générées par un modèle, avec graine ; signalées par un bandeau |
| Hypothèse utilisateur | `user_assumption` | Paramètres ou données saisis par l'utilisateur (taux sans risque, courbe, obligation théorique…) |
| Résultat simulé | `simulated` | Sortie d'une simulation Monte Carlo |

---

## 2. Installation et lancement

### 2.1 Nouvelles dépendances

| Côté | Paquet | Usage |
|---|---|---|
| Backend | `numpy` | Calcul vectoriel, tirages aléatoires |
| Backend | `scipy` | Lois de probabilité, optimisation (SLSQP, Brent, programmation linéaire) |
| Backend | `httpx` | Requis par `fastapi.testclient` pour les tests d'API |
| Frontend | `recharts` | Graphiques (histogrammes, éventails, frontière efficiente…) |

### 2.2 Avec Docker (méthode du README)

Après un `git pull` de la branche :

```bash
docker compose build backend                  # installe numpy, scipy, httpx
docker compose run --rm frontend npm install  # installe recharts dans le volume node_modules
docker compose up -d
docker compose exec backend alembic upgrade head   # crée actuarial_runs et bond_terms
```

> La validation sous Docker n'a pas encore été faite (voir [§14](#14-reste-à-faire)).

### 2.3 Sans Docker (développement local)

Le module a été développé et testé ainsi, avec PostgreSQL 16 en local :

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows ; .venv/bin/python sous Linux/macOS
# variables de .env chargées dans le shell, DATABASE_URL pointant sur localhost
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

cd ../frontend
npm install
npx vite        # le proxy de vite.config.js vise http://backend:8000 (nom Docker) :
                # hors Docker, utiliser une configuration locale qui vise 127.0.0.1:8000
```

Points à connaître sous Windows :

- le `package-lock.json` est généré sous Linux : si Vite échoue avec
  `Cannot find module @rollup/rollup-win32-x64-msvc`, installer ce paquet avec
  `npm install --no-save @rollup/rollup-win32-x64-msvc@<version de rollup>` ;
- dans un dossier synchronisé par OneDrive, le rechargement automatique d'uvicorn
  rate parfois les nouveaux fichiers : redémarrer uvicorn après un ajout de fichier.

### 2.4 Données nécessaires

Le module lit `price_history` : il faut avoir importé les cours
(`python -m app.import_prices`, clé `TWELVEDATA_API_KEY` dans `.env`). Sans cours,
les écrans affichent « historique insuffisant » au lieu de résultats.

---

## 3. Architecture

### 3.1 Arborescence

```
backend/app/actuarial/
├── __init__.py              conventions générales du module
├── api.py                   routes FastAPI, préfixe /api/actuarial
├── models.py                tables actuarial_runs et bond_terms
├── schemas.py               schémas Pydantic (entrées et sorties)
├── stats.py                 résumés de distributions (quantiles, histogrammes, éventails)
├── risk/
│   ├── var.py               VaR historique, paramétrique, Monte Carlo
│   ├── expected_shortfall.py
│   ├── risk_metrics.py      rendements, Sharpe, Sortino, contributions, Herfindahl
│   └── backtesting.py       test de Kupiec, backtest glissant
├── stochastic/
│   ├── __init__.py          grille de temps, limites, moindres carrés
│   ├── gbm.py  vasicek.py  cir.py  hull_white.py
├── fixed_income/
│   ├── cashflows.py         échéancier, bases de calcul, coupon couru
│   ├── bond_pricing.py      prix, courbe prix-rendement
│   ├── yield_to_maturity.py
│   ├── duration.py  convexity.py
│   └── curve_shocks.py      chocs parallèles et déformations de courbe
├── optimization/
│   ├── markowitz.py         variance minimale, Sharpe maximal, rendement cible
│   └── efficient_frontier.py
├── loss_models/
│   ├── frequency.py         Poisson, binomiale négative
│   ├── severity.py          Gamma, lognormale, Pareto
│   ├── aggregate_losses.py  modèle collectif simulé
│   └── capital.py           VaR, TVaR, capital économique
└── services/                accès aux données existantes et assemblage
    ├── market_data_service.py      lecture assets / price_history
    ├── portfolio_risk_service.py   portefeuilles, positions, tableau de bord
    ├── risk_analytics_service.py
    ├── stochastic_service.py
    ├── fixed_income_service.py
    ├── optimization_service.py
    ├── loss_model_service.py
    ├── lab_service.py              catalogue et exécution uniforme
    └── runs.py                     historique des calculs

frontend/src/
├── pages/actuariat/         une page par onglet + ActuarialLayout + actuariat.css
├── components/actuarial/    ActuarialCharts.jsx (graphiques), Controls.jsx (formulaires)
├── hooks/useActuarialRefs.js
└── services/actuarial.js    appels API et formatage

backend/alembic/versions/7b1e4a2c9d10_add_actuarial_tables.py
backend/tests/test_actuarial_*.py   (6 fichiers)
```

### 3.2 Découpage en couches

```
Navigateur (React)
   │  fetch /api/actuarial/...  (JWT dans l'en-tête Authorization)
   ▼
api.py ─────────── validation Pydantic, authentification, codes HTTP
   │
services/ ──────── lecture des données existantes, assemblage des résultats,
   │               historique des calculs
   ▼
risk/ stochastic/ fixed_income/ optimization/ loss_models/
                   fonctions mathématiques pures : tableaux numpy en entrée,
                   aucun accès à la base → testables sans base de données
```

Les fonctions mathématiques ne connaissent ni la base ni FastAPI. C'est ce qui
permet de les tester contre des valeurs analytiques connues.

### 3.3 Intégration avec les autres modules

| Module existant | Réutilisation | Mode |
|---|---|---|
| Market Data | `assets`, `price_history` | Lecture seule ; aucun second système d'import |
| Portfolio | `portfolios`, `positions`, `get_current_price` | Lecture seule |
| Trading | `transactions` (gains réalisés, nombre d'ordres) | Lecture seule ; aucun ordre passé |
| Risque Portfolio (`services/risk.py`) | `annualized_volatility`, `max_drawdown`, `value_curve`, `TRADING_DAYS_PER_YEAR` | Fonctions importées, non modifiées |
| Obligations | `coupon_payments` (coupons reçus par l'utilisateur) | Lecture seule |
| Authentification | `get_current_user`, `require_admin` | Dépendances FastAPI existantes |
| Stress testing bancaire | `banks` | Pas encore utilisé (voir [§14](#14-reste-à-faire)) |

Fichiers existants modifiés (modifications minimales) :

| Fichier | Modification |
|---|---|
| `backend/app/main.py` | 2 lignes : import et enregistrement du routeur |
| `backend/alembic/env.py` | 1 ligne : import des modèles du module |
| `backend/requirements.txt` | `numpy`, `scipy`, `httpx` |
| `frontend/package.json`, `package-lock.json` | `recharts` |
| `frontend/src/App.jsx` | La route `/actuariat` (page vide) devient des routes imbriquées chargées à la demande |

---

## 4. Conventions communes

Ces conventions s'appliquent à tous les sous-modules. Elles sont aussi rappelées
en bas de chaque écran (panneau « Hypothèses et conventions de calcul »).

### 4.1 Rendements et pertes

| Grandeur | Définition |
|---|---|
| Rendement simple quotidien | r_t = P_t / P_{t−1} − 1 (cours de clôture) |
| Rendement logarithmique | x_t = ln(P_t / P_{t−1}) (GBM, Monte Carlo) |
| Perte | L = −r (positive quand on perd) |
| Jours de bourse par an | 252 |
| Résultats | Fractions (0,023 = 2,3 %) ; montants dans la devise des cours (USD) |

### 4.2 Alignement des séries

Pour plusieurs actifs, seules les **dates communes** à tous les actifs sont
conservées. Il n'y a ni interpolation ni remplissage. Un actif avec moins de deux
cours est exclu et signalé.

### 4.3 Portefeuille

- Poids = valeur de marché de la position / valeur totale (liquidités comprises).
- **Hypothèse de simulation historique** : la composition actuelle est appliquée à
  tout l'historique, comme pour la courbe de performance de l'écran Portefeuille.
- Les liquidités ont un rendement nul.
- Une position sans cours, ou sans historique suffisant, est traitée comme des
  liquidités dans les mesures de risque, et signalée par un avertissement.

### 4.4 Quantiles, VaR et Expected Shortfall

- VaR_α = quantile d'ordre α des pertes, méthode `inverted_cdf` : plus petite
  perte l telle que P(L ≤ l) ≥ α. Aucune interpolation entre deux observations.
- ES_α = E[L | L ≥ VaR_α], la moyenne des pertes au-delà de la VaR (le quantile
  lui-même inclus). Par construction, ES ≥ VaR.
- La VaR n'est pas bornée à 0 : une VaR négative signifie que même le quantile
  défavorable est un gain.
- Niveaux disponibles : 95 % et 99 % pour la VaR de marché ; 95 %, 99 %, 99,5 % et
  99,9 % pour le capital économique.

> **Écart avec l'écran Portefeuille.** La VaR de `/trading/risk` lit le quantile par
> indice et la borne à 0. Sur un petit échantillon, les deux chiffres peuvent
> légèrement différer. Sur les données de démonstration du 11/11/2026, ils sont
> identiques (VaR 95 % à 1 jour de 0,73 %).

### 4.5 Horizon

| Méthode | Passage de 1 jour à h jours |
|---|---|
| Historique | Règle de la racine du temps : VaR_h = VaR_1 × √h (rendements i.i.d.) |
| Paramétrique | Moyenne μh, écart-type σ√h |
| Monte Carlo | Rendements log simulés directement sur h jours, puis composés |

### 4.6 Reproductibilité

Toutes les simulations acceptent une **graine** (`seed`, 42 par défaut). Même
modèle, mêmes paramètres et même graine donnent exactement le même résultat. Une
graine vide donne un tirage différent à chaque calcul. Les graines sont enregistrées
dans l'historique des calculs.

### 4.7 Minimum de données

En dessous de **30 jours communs d'historique**, les indicateurs de risque ne sont
pas calculés : la page affiche un avertissement plutôt qu'un chiffre peu fiable.

---

## 5. Sous-modules

### 5.1 Tableau de bord actuariel

**Écran** : `/actuariat` · **API** : `GET /api/actuarial/dashboard`

Indicateurs calculés à chaque appel sur le portefeuille de l'utilisateur.

| Indicateur | Formule |
|---|---|
| Valeur totale | Liquidités + Σ quantité × dernier cours |
| Rendement sur la période | Π(1 + r_t) − 1 |
| Rendement annualisé | (1 + R)^(252/T) − 1 (géométrique) |
| Volatilité annualisée | écart-type(r) × √252 (fonction de `services/risk.py`) |
| VaR historique | voir [§4.4](#44-quantiles-var-et-expected-shortfall) |
| Expected Shortfall | voir [§4.4](#44-quantiles-var-et-expected-shortfall) |
| Drawdown maximal | plus forte chute d'un sommet au creux suivant (fonction de `services/risk.py`) |
| Sharpe | moyenne(r − rf/252) / écart-type(r) × √252 |
| Sortino | moyenne(r − rf/252) / √moyenne(min(r − rf/252, 0)²) × √252 |
| Concentration | Herfindahl Σ w_i² sur les positions (hors liquidités) : 1/N si égal, 1 si une seule ligne |
| Contributions au risque | décomposition d'Euler, voir [§5.2](#52-risk-analytics) |

**Filtres** : portefeuille, période (3 mois, 6 mois, 1 an, 2 ans, tout), confiance
(95/99 %), horizon (1/10/20 jours), taux sans risque.

**Graphiques** : valeur simulée du portefeuille, exposition par classe d'actifs
(actions, obligations, matières premières, devises, liquidités), distribution des
rendements quotidiens (jours au-delà de la VaR en rouge), facteurs de risque.

**Intégration Trading** : nombre de transactions et total des gains réalisés
(`transactions.realized_pnl`).

**Taux sans risque** : aucune courbe de taux n'est stockée dans l'application. Le
taux est donc une hypothèse de l'utilisateur, 0 par défaut, signalée par un badge
dès qu'il est modifié.

### 5.2 Risk Analytics

**Écran** : `/actuariat/risque` · **API** : `GET /portfolio-risk/{id}`, `POST /risk/var`

Deux modes :

- **Mon portefeuille** : composition actuelle ;
- **Panier libre** : actifs et poids quelconques (normalisés à 100 %), montant exposé
  au choix. C'est un exercice : aucun ordre n'est passé.

#### VaR et Expected Shortfall

Les trois méthodes sont calculées pour toutes les combinaisons (95/99 % × 1/10/20
jours), soit 18 couples VaR/ES.

| Méthode | VaR | ES | Hypothèse principale |
|---|---|---|---|
| Historique | quantile empirique des pertes × √h | moyenne des pertes ≥ VaR, × √h | La distribution passée représente le futur |
| Paramétrique | −μh + z_α σ√h | −μh + σ√h · φ(z_α)/(1−α) | Rendements normaux : sous-estime les queues épaisses |
| Monte Carlo | quantile des pertes simulées | moyenne des pertes simulées ≥ VaR | Rendements log multinormaux N(μh, Σh), corrélations constantes |

Monte Carlo, en détail :

1. estimation de μ (vecteur) et Σ (matrice) sur les rendements log quotidiens des
   actifs ;
2. tirage de n vecteurs N(μh, Σh) (décomposition en valeurs propres) ;
3. rendement simple de chaque actif = exp(x) − 1 ;
4. rendement du portefeuille = Σ w_i (exp(x_i) − 1), poids constants sur l'horizon.

Un seul tirage par horizon est partagé par les deux niveaux de confiance. La graine
de l'horizon h est `seed + h`.

#### Contributions au risque (décomposition d'Euler)

| Grandeur | Formule | Propriété |
|---|---|---|
| Volatilité du portefeuille | σ_p = √(wᵀΣw) | — |
| Contribution marginale | MRC_i = (Σw)_i / σ_p | Effet d'une petite hausse du poids i |
| Contribution totale | RC_i = w_i × MRC_i | Σ RC_i = σ_p |
| Part du risque | RC_i / σ_p | Somme = 100 % |

Les contributions sont annualisées (× √252).

#### Backtesting de la VaR (test de Kupiec)

1. Pour chaque jour t après une fenêtre de W jours (100 par défaut), la VaR
   historique à 1 jour est calculée sur les W rendements précédents.
2. Une **exception** est comptée si la perte du jour dépasse cette VaR.
3. Test de couverture inconditionnelle de Kupiec, avec x exceptions sur n jours et
   p = 1 − α :

   LR = −2 ln[(1−p)^(n−x) p^x] + 2 ln[(1−x/n)^(n−x) (x/n)^x] ~ χ²(1)

4. Le modèle est **rejeté au seuil de 5 %** si la p-valeur est inférieure à 0,05.

Le graphique montre les pertes quotidiennes (exceptions en rouge) et la VaR prévue.

Autres éléments de l'écran : matrice de corrélation (carte de chaleur), risque de
chaque actif pris isolément (rendement, volatilité, VaR, drawdown), distribution
Monte Carlo avec la zone au-delà de la VaR.

### 5.3 Modèles stochastiques

**Écran** : `/actuariat/stochastique` · **API** : `POST /stochastic/calibrate`, `POST /stochastic/simulate`

Toutes les simulations utilisent les **lois de transition exactes**, sans erreur de
discrétisation. Le temps est en années et les paramètres sont annualisés.

#### GBM — prix d'un actif

| | |
|---|---|
| Dynamique | dS = μS dt + σS dW |
| Simulation | S(t+Δ) = S(t) · exp((μ − σ²/2)Δ + σ√Δ Z) |
| Calibration (maximum de vraisemblance) | σ² = Var(x)/Δ ; μ = moyenne(x)/Δ + σ²/2, sur les rendements log x |
| Erreurs standards | se(μ) ≈ σ/√T ; se(σ) ≈ σ/√(2(n−1)) |
| Valeurs théoriques affichées | E[S_T] = S₀e^(μT) ; P(S_T < S₀) (loi lognormale) |
| Données | **Cours réels** de l'actif choisi ; S₀ = dernier cours |

> Sur un an d'historique, l'erreur standard de μ est du même ordre que σ (par
> exemple ±13,8 % pour SPY). La dérive estimée est donc très imprécise ; c'est
> affiché à côté de la calibration.

#### Vasicek — taux court

| | |
|---|---|
| Dynamique | dr = a(b − r) dt + σ dW |
| Transition exacte | r(t+Δ) = r(t)e^(−aΔ) + b(1 − e^(−aΔ)) + σ√((1 − e^(−2aΔ))/(2a)) · Z |
| Moments | E[r_t] = b + (r₀ − b)e^(−at) ; Var[r_t] = σ²/(2a) · (1 − e^(−2at)) |
| Zéro-coupon | P(0,T) = A·e^(−B r₀), B = (1 − e^(−aT))/a, A = exp((b − σ²/(2a²))(B − T) − σ²B²/(4a)) |
| Calibration | AR(1) r_{t+1} = c + φ r_t + ε par moindres carrés : a = −ln φ/Δ, b = c/(1 − φ), σ = sd(ε)·√(2a/(1 − φ²)) ; exige 0 < φ < 1 |
| Particularité | Taux gaussien : peut devenir négatif (probabilité affichée) |

#### CIR — taux court positif

| | |
|---|---|
| Dynamique | dr = a(b − r) dt + σ√r dW |
| Condition de Feller | 2ab ≥ σ² ⇒ le taux reste strictement positif (avertissement sinon) |
| Transition exacte | r(t+Δ) = c·X, X ~ χ²'(d, λ), c = σ²(1 − e^(−aΔ))/(4a), d = 4ab/σ², λ = r(t)e^(−aΔ)/c |
| Moments | même moyenne que Vasicek ; Var = r₀σ²/a (e^(−at) − e^(−2at)) + bσ²/(2a)(1 − e^(−at))² |
| Zéro-coupon | formule fermée de Cox-Ingersoll-Ross (γ = √(a² + 2σ²)) |
| Calibration | régression (Δr)/√r = β₁/√r + β₂√r + ε : a = −β₂/Δ, b = −β₁/β₂, σ = sd(ε)/√Δ ; série strictement positive |

#### Hull-White à un facteur

| | |
|---|---|
| Dynamique | dr = (θ(t) − a r) dt + σ dW |
| Ajustement | θ(t) choisi pour reproduire exactement la courbe zéro-coupon initiale P(0,T) = e^(−R(T)T) |
| Décomposition | r(t) = x(t) + α(t), x processus d'Ornstein-Uhlenbeck (x₀ = 0), α(t) = f(0,t) + σ²/(2a²)(1 − e^(−at))² |
| Courbe initiale | Saisie par l'utilisateur (taux zéro-coupon continus), interpolée linéairement, prolongée à plat ; forward f(0,t) = d/dt[R(t)t] par différence centrée |
| Calibration | a et σ comme Vasicek sur une série historique ; θ(t) par la courbe |
| Contrôle | E[exp(−∫r dt)] simulé = P(0,T) de la courbe (vérifié par les tests) |

#### Données des modèles de taux

**L'application ne stocke aucune série de taux d'intérêt.** Les modèles de taux sont
donc :

- soit paramétrés à la main (valeurs de départ indicatives, badge « Hypothèse
  utilisateur ») ;
- soit calibrés sur une série que l'utilisateur colle dans la page (en %, avec sa
  périodicité : quotidienne, hebdomadaire ou mensuelle).

#### Résultats affichés

- Éventail des trajectoires (bandes 5–95 % et 25–75 %, médiane, moyenne,
  12 trajectoires individuelles) et distribution à l'horizon.
- Statistiques à l'horizon : moyenne et intervalle de confiance à 95 % de la moyenne
  (± 1,96 × écart-type/√n), intervalle à 90 % des valeurs, écart-type, **comparés aux
  valeurs théoriques**.
- GBM : probabilité de perte (simulée et théorique) et VaR 95 % relative.
- Taux : probabilité de taux négatif et prix zéro-coupon simulé, comparé à la
  formule fermée (Vasicek, CIR) ou à la courbe initiale (Hull-White).
- **Analyse de sensibilité** : volatilité σ × 0,5 / 0,75 / 1 / 1,25 / 1,5, avec les
  mêmes tirages aléatoires (2 000 trajectoires au plus). Les écarts mesurent donc
  l'effet de σ et non le bruit de simulation.

### 5.4 Fixed Income Analytics

**Écran** : `/actuariat/obligations` · **API** : `GET /fixed-income/bonds`, `GET /fixed-income/{id}`, `POST /fixed-income/analyze`, `PUT /fixed-income/{id}/terms`

#### Règle : ne rien inventer

Les obligations du référentiel (**TLT, SHY, LQD, HYG**) sont des **ETF** obligataires.
Ils n'ont ni coupon, ni échéance, ni valeur nominale uniques. Pour eux, l'écran
affiche :

- les statistiques de marché calculées sur les cours réels (dernier cours,
  rendement, volatilité, drawdown) ;
- les coupons reçus par l'utilisateur, lus dans `coupon_payments` ;
- le message « caractéristiques contractuelles non disponibles ».

Les calculs contractuels portent sur :

- une **obligation théorique** saisie par l'utilisateur (badge « Hypothèse
  utilisateur ») ;
- ou une obligation du référentiel dont un administrateur a renseigné les
  caractéristiques dans `bond_terms`, avec leur source obligatoire. Dans ce cas, le
  dernier cours est interprété comme un prix pied de coupon, dans la même unité que
  le nominal.

#### Conventions

| Élément | Convention |
|---|---|
| Coupon | nominal × taux / fréquence (fréquences 1, 2, 4 ou 12) |
| Dates de coupon | en reculant depuis l'échéance par pas de 12/f mois (jour borné au dernier jour du mois) |
| Temps des flux | années depuis la date de règlement, base ACT/365, ACT/360 ou 30/360 |
| Actualisation | DF(t) = (1 + y/f)^(−f·t) (composition périodique) |
| Prix plein (dirty) | Σ flux × DF |
| Coupon couru | coupon × jours écoulés / jours de la période en cours |
| Prix pied de coupon (clean) | prix plein − coupon couru |

#### Formules

| Mesure | Formule |
|---|---|
| YTM | y tel que prix plein(y) = prix observé ; méthode de Brent sur [−50 %, 200 %] |
| Duration de Macaulay | D = Σ t_i · VA_i / P |
| Duration modifiée | D_mod = D / (1 + y/f) |
| DV01 | D_mod × P × 0,0001 |
| Convexité | C = Σ CF_i · t_i(t_i + 1/f) · DF_i / (P(1 + y/f)²) |
| Approximation | ΔP/P ≈ −D_mod·Δy + ½·C·Δy² |

#### Sensibilité et chocs

- **Chocs parallèles** de ±25, ±50, ±100 et ±200 pb : réévaluation complète, comparée
  à l'approximation par la duration seule et à l'approximation duration + convexité
  (erreur affichée).
- **Déformations de courbe** d'amplitude Δ (100 pb par défaut) :

  | Scénario | Profil de choc s(t) |
  |---|---|
  | Parallèle | Δ |
  | Pentification | Δ × clip((t − 5)/5, −1, 1) : court terme −Δ, long terme +Δ, pivot 5 ans |
  | Aplatissement | opposé de la pentification |
  | Papillon | +Δ hors de [2, 10] ans, −Δ entre les deux |

  La courbe de départ est celle que saisit l'utilisateur ou, à défaut, une courbe
  plate au YTM (signalée comme hypothèse).

**Exemple vérifié** (règlement le 11/11/2026, coupon 4 % semestriel, échéance
15/05/2036, YTM 4,5 %) : prix pied de coupon 96,15 ; duration de Macaulay 7,81 ans ;
convexité 70,29.

### 5.5 Optimisation de portefeuille

**Écran** : `/actuariat/optimisation` · **API** : `POST /optimization/markowitz`

#### Modèle de Markowitz

| Entrée | Estimation |
|---|---|
| Rendements espérés | μ = moyenne des rendements quotidiens × 252 |
| Covariance | Σ = covariance quotidienne × 252 |

| Problème | Formulation |
|---|---|
| Variance minimale | min wᵀΣw |
| Sharpe maximal | max (wᵀμ − rf) / √(wᵀΣw) |
| Rendement cible | min wᵀΣw sous wᵀμ = cible |

Résolution numérique par SLSQP (`scipy.optimize.minimize`), départ à poids égaux.

**Contraintes** :

- Σ w_i = 100 % ;
- positions longues par défaut : 0 ≤ w_i ≤ w_max ;
- vente à découvert possible **en simulation théorique uniquement** :
  −w_max ≤ w_i ≤ w_max ;
- faisabilité : n × w_max ≥ 100 %, sinon message « Infaisable ».

**Frontière efficiente** : portefeuilles de variance minimale pour une grille de
rendements cibles, du portefeuille de variance minimale au rendement maximal
atteignable sous les mêmes contraintes (programme linéaire, `linprog`). Les points
non résolus sont omis, jamais approximés.

**Univers** : actifs détenus et valorisés, plus les actifs ajoutés par l'utilisateur
(au moins deux actifs avec historique).

**Comparaison** : l'allocation actuelle (poids de la partie investie, hors
liquidités) est placée sur le graphique de la frontière et dans le tableau des poids.

**Rééquilibrage indicatif** : quantités cibles pour atteindre le portefeuille de
Sharpe maximal, sur le montant investi aux derniers cours. **Aucun ordre n'est
passé** ; l'écran le rappelle par un bandeau.

> **Mise en garde.** Les poids optimaux sont très sensibles aux erreurs d'estimation
> de μ, et un an d'historique estime μ très mal. Le résultat est un exercice
> pédagogique, pas une recommandation d'investissement.

### 5.6 Modèles de pertes et capital économique

**Écran** : `/actuariat/pertes` · **API** : `POST /loss-model/fit`, `POST /loss-model/simulate`

#### Modèle collectif

S = X₁ + … + X_N, avec N (nombre de pertes) indépendant des montants X_i, et les X_i
indépendants et de même loi.

- E[S] = E[N]·E[X]
- Var[S] = E[N]·Var[X] + Var[N]·E[X]²

Ces moments théoriques sont comparés au résultat simulé.

#### Étape 1 — données de pertes

| Source | Construction | Provenance |
|---|---|---|
| **Pertes de marché réelles** | Événement = jour où la perte du portefeuille (ou d'un actif) dépasse un seuil (1 % par défaut). Sévérité = montant perdu ce jour-là. Fréquence = nombre d'événements par mois civil (mois sans événement compris) ; 12 périodes par an. | `real_market_data` |
| **Données saisies** | Nombres de pertes par période et montants, collés dans la page | `user_assumption` |
| **Données synthétiques** | Tirées des lois et paramètres choisis, avec graine ; bandeau d'avertissement | `synthetic` |

> Hypothèse simplificatrice des pertes de marché : les événements sont supposés
> indépendants. En réalité, la volatilité se regroupe dans le temps (périodes de
> crise).

#### Étape 2 — ajustement des lois

**Fréquence**

| Loi | Paramètres | Moments | Estimation |
|---|---|---|---|
| Poisson(λ) | λ | E = Var = λ | λ = moyenne (maximum de vraisemblance) |
| Binomiale négative(r, p) | r, p | E = r(1−p)/p ; Var = E + E²/r | Maximum de vraisemblance profilé : p = r/(r + moyenne), r optimisé. Exige Var > moyenne (surdispersion) |

**Sévérité**

| Loi | Paramètres | Moyenne | Estimation | Queue |
|---|---|---|---|---|
| Gamma | forme k, échelle θ | kθ | Maximum de vraisemblance numérique | Fine |
| Lognormale | μ, σ (de ln X) | e^(μ + σ²/2) | Formules fermées sur ln X | Modérée |
| Pareto (type I) | α, x_m | αx_m/(α−1) si α > 1 | x_m = seuil connu (pertes de marché) ou plus petit montant ; α = n / Σ ln(x_i/x_m) | Épaisse ; moyenne infinie si α ≤ 1, variance infinie si α ≤ 2 |

**Qualité d'ajustement** :

- log-vraisemblance et **AIC = 2k − 2 ln L** (plus petit = meilleur). La meilleure
  loi est surlignée et reprise automatiquement pour la simulation ;
- statistique de **Kolmogorov-Smirnov** et sa p-valeur pour la sévérité. Cette
  p-valeur est optimiste, car les paramètres sont estimés sur les mêmes données :
  elle est seulement indicative.

Un avertissement s'affiche avec moins de 24 périodes ou moins de 30 montants.

**Exemple sur les données réelles** (portefeuille de démonstration, seuil 0,5 %) :
13 mois, 29 événements, dispersion 2,03. La binomiale négative (AIC 54,2) l'emporte
sur Poisson (55,0), et Pareto (α = 2,29) l'emporte sur la lognormale et la Gamma.

#### Étape 3 — simulation de la perte annuelle

- **Annualisation de la fréquence** (somme de k périodes indépendantes) : Poisson(kλ),
  binomiale négative (k·r, p).
- Pour chaque année simulée : N tiré, puis N montants tirés et sommés.
- **Franchise d et plafond L par sinistre** (optionnels) : perte retenue
  = min(max(X − d, 0), L).

#### Mesures de risque et capital économique

| Mesure | Définition |
|---|---|
| VaR_α(S) | quantile d'ordre α de la perte annuelle |
| TVaR_α(S) | moyenne de S au-delà de VaR_α |
| **Capital économique** | **VaR₉₉,₅ %(S) − E[S]**, la perte inattendue (convention Solvabilité II à un an ; la perte attendue est supposée couverte par les primes ou les provisions) |
| Variante | TVaR₉₉,₅ %(S) − E[S] |

#### Stress testing des hypothèses

Cinq scénarios par défaut, modifiables (8 au plus) :

| Scénario | Fréquence × | Sévérité × | Queue × |
|---|---|---|---|
| Central | 1 | 1 | 1 |
| Fréquence +50 % | 1,5 | 1 | 1 |
| Sévérité +50 % | 1 | 1,5 | 1 |
| Queue épaissie +25 % | 1 | 1 | 1,25 |
| Combiné adverse | 1,5 | 1,5 | 1,25 |

Application des multiplicateurs :

| Multiplicateur | Effet |
|---|---|
| Fréquence × m | Moyenne de N multipliée par m (Poisson : λm ; binomiale négative : r fixé, p recalculé) |
| Sévérité × s | Échelle multipliée : θs (Gamma), μ + ln s (lognormale), x_m·s (Pareto) |
| Queue × t | Dispersion accrue : coefficient de variation × t (Gamma, moyenne conservée), σ·t (lognormale), α/t (Pareto) |

Tous les scénarios utilisent **la même graine et le même nombre d'années** que la
référence centrale. L'écart de capital mesure donc l'effet du choc et non le bruit
Monte Carlo : le scénario central affiche exactement 0 %.

### 5.7 Laboratoire de modèles

**Écran** : `/actuariat/laboratoire` · **API** : `GET /lab/catalog`, `POST /lab/run`, `POST /lab/compare`, `GET /lab/runs`

#### Catalogue (13 modèles)

| Famille | Modèles | Cible |
|---|---|---|
| Value at Risk | VaR historique, paramétrique, Monte Carlo | Portefeuille ou panier d'actifs |
| Modèles stochastiques | GBM | Un actif (calibration automatique si paramètres vides) |
| | Vasicek, CIR, Hull-White | Paramètres saisis |
| Optimisation | Markowitz (Sharpe maximal) | Portefeuille + actifs ajoutés |
| Fréquence des pertes | Poisson, binomiale négative | Paramètres saisis |
| Sévérité des pertes | Gamma, lognormale, Pareto | Paramètres saisis |

Le catalogue (`lab_service.CATALOG`) est la **source unique** des formules,
hypothèses et paramètres par défaut. L'écran le lit depuis l'API.

#### Fonctionnement

1. Jusqu'à **6 configurations** : modèle, cible, paramètres, confiance et horizon
   (VaR), horizon et pas (stochastique), nombre de simulations, graine.
2. **Lancer et comparer** : toutes les configurations sont exécutées. Une
   configuration en erreur est signalée sans empêcher les autres.
3. Résultats :
   - tableau comparatif (une colonne par modèle, « — » si l'indicateur ne s'applique
     pas) ;
   - un histogramme par modèle (zone au-delà de la VaR en rouge pour les VaR) ;
   - formule, hypothèses et paramètres utilisés.
4. **Export** :
   - **CSV** de la comparaison : séparateur `;` et BOM UTF-8, pour une ouverture
     directe dans Excel en français ;
   - **JSON** complet (requêtes et résultats).
5. **Historique** : les 20 derniers calculs de l'utilisateur, tous écrans confondus.
   - « Recharger » recrée une configuration identique (même graine, donc même
     résultat).
   - « JSON » télécharge le calcul.

Le laboratoire ne contient aucune formule propre : il appelle les mêmes fonctions
que les autres écrans. Les VaR du laboratoire sont donc identiques à celles de
Risk Analytics.

---

## 6. Référence de l'API

Toutes les routes sont préfixées par **`/api/actuarial`** et exigent un jeton JWT
(`Authorization: Bearer <jeton>`). Elles sont visibles dans la documentation
interactive FastAPI : `http://localhost:8000/docs`, section **actuarial**.

### 6.1 Codes d'erreur

| Code | Cas |
|---|---|
| 401 / 403 | Jeton absent, invalide ou expiré ; 403 sur la route réservée aux administrateurs |
| 404 | Portefeuille inexistant **ou appartenant à un autre utilisateur** ; actif ou obligation introuvable |
| 422 | Paramètre invalide (Pydantic) ou donnée insuffisante ; le champ `detail` explique la cause en français |

### 6.2 Vue d'ensemble

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/portfolios` | Portefeuilles de l'utilisateur |
| GET | `/assets` | Actifs et étendue de leur historique |
| GET | `/dashboard` | Tableau de bord |
| GET | `/portfolio-risk/{portfolio_id}` | Rapport de risque complet du portefeuille |
| POST | `/risk/var` | VaR/ES d'un panier libre |
| POST | `/risk/expected-shortfall` | Identique à `/risk/var` (renvoie VaR et ES) |
| POST | `/stochastic/calibrate` | Calibration d'un modèle stochastique |
| POST | `/stochastic/simulate` | Simulation Monte Carlo |
| GET | `/fixed-income/bonds` | Obligations du référentiel |
| GET | `/fixed-income/{asset_id}` | Détail d'une obligation du référentiel |
| POST | `/fixed-income/analyze` | Analyse d'une obligation théorique |
| PUT | `/fixed-income/{asset_id}/terms` | **Administrateurs** : caractéristiques contractuelles |
| POST | `/optimization/markowitz` | Optimisation et frontière efficiente |
| POST | `/loss-model/fit` | Jeu de pertes et ajustement des lois |
| POST | `/loss-model/simulate` | Perte annuelle, capital, stress |
| GET | `/lab/catalog` | Catalogue des modèles |
| POST | `/lab/run` | Exécution d'un modèle |
| POST | `/lab/compare` | Exécution de 1 à 6 modèles |
| GET | `/lab/runs` | Historique des calculs de l'utilisateur |

### 6.3 Détail des paramètres

#### `GET /dashboard`

| Paramètre | Type | Défaut | Valeurs |
|---|---|---|---|
| `portfolio_id` | entier | premier portefeuille | portefeuille de l'utilisateur |
| `lookback` | entier | 252 | 0 à 5000 jours ; 0 = tout l'historique |
| `confidence` | décimal | 0.95 | 0.95 ou 0.99 |
| `horizon` | entier | 1 | 1, 10 ou 20 |
| `risk_free_rate` | décimal | 0 | −0,05 à 0,20 |

Réponse (extrait) :

```json
{
  "portfolio_id": 1, "data_source": "real_market_data",
  "total_value": 100000.0, "observations": 250,
  "period_start": "2025-11-12", "period_end": "2026-11-10",
  "metrics": {
    "cumulative_return": 0.0408, "annualized_volatility": 0.0755,
    "var": 0.0073, "var_amount": 732.62,
    "expected_shortfall": 0.0107, "max_drawdown": 0.0476,
    "sharpe_ratio": 0.5716, "sortino_ratio": 0.8158
  },
  "exposure": [{"asset_class": "cash", "value": 50729.01, "weight": 0.507}],
  "risk_contributions": [{"symbol": "AAPL", "weight": 0.209, "risk_share": 0.527}],
  "warnings": []
}
```

`metrics` vaut `null` si l'historique compte moins de 30 jours ou si le portefeuille
n'a aucune position ; `warnings` explique alors pourquoi.

#### `GET /portfolio-risk/{portfolio_id}`

Mêmes paramètres que `/dashboard`, plus :

| Paramètre | Défaut | Valeurs |
|---|---|---|
| `n_simulations` | 10 000 | 1 000 à 50 000 |
| `seed` | 42 | 0 à 2³¹−1 ; absent = non reproductible |
| `backtest_window` | 100 | 30 à 1000 jours |

Réponse : `var_table` (18 lignes : méthode × confiance × horizon), `metrics`,
`monte_carlo_distribution` (histogramme `{from, to, count}`), `assets`, `correlation`,
`risk_contributions`, `backtest` (statistique de Kupiec et série jour par jour, ou
`null` si l'historique est trop court), `warnings`.

#### `POST /risk/var`

```json
{
  "symbols": ["SPY", "TLT"], "weights": [60, 40], "notional": 100000,
  "lookback": 252, "confidence": 0.99, "horizon": 10,
  "n_simulations": 10000, "seed": 42, "risk_free_rate": 0, "backtest_window": 100
}
```

`symbols` : 1 à 20 actifs distincts. `weights` est facultatif (poids égaux), et les
poids sont normalisés à 100 %. Même réponse que `/portfolio-risk`.

#### `POST /stochastic/calibrate`

```json
{"model": "gbm", "symbol": "AAPL", "lookback": 252}
{"model": "vasicek", "series": [0.031, 0.032, 0.030, 0.033], "dt": 0.0833}
```

| Champ | Usage |
|---|---|
| `model` | `gbm`, `vasicek`, `cir`, `hull_white` |
| `symbol` | GBM uniquement |
| `series` | Modèles de taux : taux en fractions, 10 à 20 000 valeurs |
| `dt` | Pas de la série en années (1/252, 1/52, 1/12…) |

Réponse : `params`, `standard_errors` (GBM), `observations`, `notes`, `data_source`.

#### `POST /stochastic/simulate`

```json
{
  "model": "cir",
  "params": {"r0": 0.03, "a": 0.6, "b": 0.04, "sigma": 0.05},
  "horizon": 2, "steps": 24, "n_simulations": 5000, "seed": 42
}
```

| Modèle | Paramètres obligatoires |
|---|---|
| `gbm` | `s0`, `mu`, `sigma` |
| `vasicek`, `cir` | `r0`, `a`, `b`, `sigma` |
| `hull_white` | `a`, `sigma`, `curve_maturities`, `curve_rates` |

Limites : `horizon` ≤ 50 ans, `steps` ≤ 2 520, `n_simulations` ≤ 20 000,
`n_simulations × steps` ≤ 5 040 000.

Réponse : `fan` (quantiles par date), `sample_paths`, `terminal` (statistiques),
`terminal_histogram`, `analytics` (valeurs théoriques), `sensitivity`.

#### `GET /fixed-income/{asset_id}`

Paramètre `settlement_date` (date, défaut aujourd'hui). Réponse : `market`,
`coupons`, `terms` (ou `null`), `analysis` (ou `null`), `message`.

#### `POST /fixed-income/analyze`

```json
{
  "bond": {
    "face_value": 100, "coupon_rate": 0.04, "coupon_frequency": 2,
    "maturity_date": "2036-05-15", "issue_date": null, "day_count": "ACT/365"
  },
  "settlement_date": "2026-11-11",
  "ytm": 0.045,
  "curve_maturities": [1, 5, 10], "curve_rates": [0.03, 0.035, 0.04],
  "shock_bp": 100
}
```

Fournir **soit** `ytm` **soit** `clean_price`, pas les deux. La courbe est facultative.

Réponse : `ytm`, `clean_price`, `dirty_price`, `accrued_interest`,
`macaulay_duration`, `modified_duration`, `convexity`, `dv01`, `cash_flows`,
`price_yield_curve`, `parallel_sensitivity`, `curve_scenarios`, `curve_source`.

#### `PUT /fixed-income/{asset_id}/terms` (administrateurs)

Corps de requête : celui de `bond` ci-dessus, plus `source` (3 à 255 caractères,
**obligatoire** : prospectus, site de l'émetteur…). Crée ou remplace la ligne
`bond_terms` de l'actif, qui doit être de type obligation.

#### `POST /optimization/markowitz`

```json
{
  "portfolio_id": 1, "extra_symbols": ["SPY", "EWJ", "HYG"], "lookback": 252,
  "risk_free_rate": 0, "max_weight": 0.4, "allow_short": false,
  "target_return": 0.10, "frontier_points": 25
}
```

| Champ | Valeurs |
|---|---|
| `max_weight` | 0,05 à 1 |
| `extra_symbols` | 30 actifs au plus |
| `frontier_points` | 5 à 60 |
| `target_return` | facultatif, −1 à 5 |

Réponse : `assets` (μ, σ), `correlation`, `current`, `optimized` (`min_variance`,
`max_sharpe`, éventuellement `target_return`), `frontier`, `rebalance`, `warnings`.

#### `POST /loss-model/fit`

```json
{"source": "market", "threshold": 0.01, "symbol": null, "portfolio_id": null, "notional": null, "lookback": 0}
{"source": "manual", "counts": [2, 0, 3, 1], "amounts": [1250, 830, 4100, 600, 980, 2300], "periods_per_year": 12}
{"source": "synthetic", "frequency_model": "poisson", "frequency_params": {"lam": 4},
 "severity_model": "gamma", "severity_params": {"shape": 2, "scale": 1000}, "periods": 60, "seed": 42}
```

Pour `market` : sans `symbol`, c'est le portefeuille de l'utilisateur qui est
analysé ; sans `notional`, la valeur exposée est celle du portefeuille (ou 100 000
pour un actif). `threshold` est compris strictement entre 0 et 0,5.

Réponse : `dataset` (description, comptages, statistiques et histogramme des
montants), `frequency_fits`, `severity_fits` (une loi non ajustable renvoie `error`
au lieu de paramètres), `best_frequency`, `best_severity`, `warnings`.

#### `POST /loss-model/simulate`

```json
{
  "frequency_model": "negative_binomial", "frequency_params": {"r": 2.77, "p": 0.554},
  "periods_per_year": 12,
  "severity_model": "pareto", "severity_params": {"alpha": 2.29, "xm": 500},
  "n_years": 20000, "seed": 42, "deductible": 0, "limit": null,
  "scenarios": [{"name": "Double fréquence", "frequency_multiplier": 2}]
}
```

| Paramètres de loi | Clés |
|---|---|
| Poisson | `lam` |
| Binomiale négative | `r`, `p` |
| Gamma | `shape`, `scale` |
| Lognormale | `mu`, `sigma` |
| Pareto | `alpha`, `xm` |

`frequency_params` s'entend **par période**. `n_years` : 1 000 à 200 000.
`scenarios` : 8 au plus, multiplicateurs ≤ 10 (queue ≤ 5) ; absents = 5 scénarios
par défaut.

Réponse : `aggregate`, `analytic`, `probability_no_loss`, `histogram`,
`risk_measures` (4 niveaux), `economic_capital`, `stress`, `severity_curve`,
`frequency_pmf`, `warnings`.

#### `POST /lab/run` et `POST /lab/compare`

```json
{
  "model": "var_monte_carlo", "symbols": ["AAPL", "TLT"], "weights": null,
  "portfolio_id": null, "lookback": 252, "confidence": 0.99, "horizon": 10,
  "horizon_years": 1, "steps": 52, "n_simulations": 5000, "seed": 42,
  "params": {}
}
```

`/lab/compare` reçoit `{"runs": [ ... 1 à 6 requêtes ... ]}` et renvoie pour chacune
`{ok, result | error, request}`.

Réponse uniforme d'une exécution : `label`, `family`, `formula`, `assumptions`,
`data_source`, `target`, `metrics` (`[{key, label, value, kind}]`, avec `kind` ∈
`pct`, `amount`, `number`, `count`), `histogram`, `marker` (position de la VaR),
`params_used`, `notes`.

#### `GET /lab/runs`

Paramètre `limit` (1 à 200, défaut 50). Calculs de l'utilisateur connecté
uniquement, du plus récent au plus ancien.

---

## 7. Base de données

### 7.1 Migration

`backend/alembic/versions/7b1e4a2c9d10_add_actuarial_tables.py`
(révision parente : `dc8d3b346bca`).

- **Additive** : deux tables créées, aucune table existante modifiée.
- Testée en montée, descente puis remontée ; `alembic check` ne détecte aucun écart
  entre modèles et base.
- Types portables (`JSON` et non `JSONB`) : les tests tournent sur SQLite.

### 7.2 Table `actuarial_runs`

Historique des calculs, pour la reproductibilité et le laboratoire.

| Colonne | Type | Contenu |
|---|---|---|
| `id` | entier, clé primaire | |
| `user_id` | FK `users`, `ON DELETE CASCADE`, indexée | Auteur du calcul |
| `portfolio_id` | FK `portfolios`, `ON DELETE SET NULL`, nullable | Portefeuille concerné |
| `model` | texte (40) | `gbm`, `markowitz`, `loss_model`, `var`, `bond`, identifiants du laboratoire… |
| `params` | JSON | Requête complète |
| `seed` | entier, nullable | Graine |
| `data_source` | texte (30) | Provenance (voir [§1.3](#13-provenance-des-données)) |
| `summary` | JSON | Indicateurs clés uniquement |
| `created_at` | horodatage | |

Les trajectoires ne sont **jamais stockées** : elles se régénèrent à l'identique avec
les paramètres et la graine enregistrés.

Écrans qui enregistrent : simulations stochastiques, VaR d'un panier, obligation
théorique, optimisation, simulation de pertes, laboratoire.

### 7.3 Table `bond_terms`

Caractéristiques contractuelles d'une obligation de `assets`. **Vide par défaut.**

| Colonne | Type | Contenu |
|---|---|---|
| `asset_id` | FK `assets`, unique | Une ligne par obligation |
| `face_value` | Numeric(18,4) | Nominal |
| `coupon_rate` | Numeric(8,6) | 0,045 pour 4,5 % par an |
| `coupon_frequency` | entier | 1, 2, 4 ou 12 |
| `issue_date` | date, nullable | Émission |
| `maturity_date` | date | Échéance |
| `day_count` | texte (20) | `ACT/365`, `ACT/360` ou `30/360` |
| `source` | texte (255) | **Provenance obligatoire** |

Alimentée uniquement par la route administrateur `PUT /fixed-income/{id}/terms`.

---

## 8. Frontend

### 8.1 Routes

| Route | Page | Fichier |
|---|---|---|
| `/actuariat` | Tableau de bord | `ActuarialDashboard.jsx` |
| `/actuariat/risque` | Risk Analytics | `RiskAnalyticsPage.jsx` |
| `/actuariat/stochastique` | Modèles stochastiques | `StochasticPage.jsx` |
| `/actuariat/obligations` | Fixed Income | `FixedIncomePage.jsx` |
| `/actuariat/optimisation` | Optimisation | `OptimizationPage.jsx` |
| `/actuariat/pertes` | Modèles de pertes | `LossModelingPage.jsx` |
| `/actuariat/laboratoire` | Laboratoire | `ModelLabPage.jsx` |

`ActuarialLayout.jsx` affiche le titre et les onglets, et enveloppe les pages dans un
`Suspense`. Le lien « Actuariat » de la barre latérale existante reste actif sur
toutes les sous-pages.

### 8.2 Chargement à la demande

Les pages du module sont chargées par `React.lazy`. `recharts` (environ 430 ko)
n'est téléchargé qu'à l'ouverture de l'Actuariat : le bundle principal des autres
écrans n'a grossi que d'environ 3 ko.

### 8.3 Composants partagés

| Fichier | Contenu |
|---|---|
| `components/actuarial/ActuarialCharts.jsx` | `SourceBadge`, `BinsHistogram`, `ReturnHistogram`, `ValueCurveChart`, `ExposureBars`, `RiskShareChart`, `CorrelationHeatmap`, `FanChart`, `FrontierChart`, `BacktestChart`, `SimpleLineChart`, `CashFlowChart` |
| `components/actuarial/Controls.jsx` | `Field`, `Kpi`, `Panel`, `Status` (chargement, erreur, avertissements), `Conventions` |
| `hooks/useActuarialRefs.js` | Portefeuilles et actifs disponibles (sélecteurs) |
| `services/actuarial.js` | `actuarialApi`, `postActuarial`, formatage français (`fmtPct`, `fmtAmount`, `fmtNum`, `fmtCompact`), conversions `percentToFraction` et `parseNumber` |

### 8.4 Règles d'interface

- Thème sombre et classes existantes réutilisés (`page`, `panel`, `stat-card`,
  `data-table`…). Les styles propres sont préfixés `act-` dans `actuariat.css`.
- Saisie à la française : virgule décimale acceptée ; taux saisis en %, convertis
  en fractions avant l'envoi.
- Chaque écran gère le chargement, les erreurs (message de l'API) et les
  avertissements (historique court, données synthétiques…).
- Responsive : grilles repliées sur une colonne sous 1 100 px, tableaux avec
  défilement horizontal, onglets défilants sur mobile.

---

## 9. Tests

### 9.1 Lancer les tests

```bash
cd backend
.venv/Scripts/python -m pytest                       # toute la suite
.venv/Scripts/python -m pytest tests/test_actuarial_*.py   # module Actuariat seul
# avec Docker :
docker compose exec backend pytest
```

Les tests utilisent une base SQLite en mémoire (`tests/conftest.py`) : ni PostgreSQL
ni réseau ne sont nécessaires.

### 9.2 Couverture

**170 tests** au total : les 65 tests existants, inchangés et tous verts, plus 105
tests du module.

| Fichier | Tests | Contenu |
|---|---|---|
| `test_actuarial_risk.py` | 17 | VaR et ES (valeurs exactes, ES de la loi normale = 2,0627), reproductibilité Monte Carlo, Sharpe, Sortino, contributions, Herfindahl |
| `test_actuarial_models.py` | 31 | GBM, Vasicek, CIR, Hull-White (moments, zéro-coupons, calibration) ; obligations (zéro-coupon, pair, duration et convexité contre différences finies, YTM aller-retour) ; Markowitz (variance minimale = inverse des variances, Sharpe maximal = portefeuille tangent) ; Kupiec |
| `test_actuarial_loss_models.py` | 16 | Lois de fréquence et de sévérité (estimateurs, AIC, moments infinis de Pareto, chocs), moyenne et variance du modèle collectif, franchise et plafond, capital |
| `test_actuarial_api.py` | 8 | Tableau de bord, authentification, validation des paramètres, isolation des portefeuilles |
| `test_actuarial_api_models.py` | 20 | Routes Risk Analytics, stochastique, Fixed Income (ETF sans caractéristiques, route administrateur), Markowitz (aucun ordre passé, contraintes, infaisabilité) |
| `test_actuarial_api_phase4.py` | 13 | Pertes de marché réelles, données saisies et synthétiques, capital et stress, laboratoire (catalogue, comparaison, calibration GBM, erreurs isolées, historique par utilisateur) |

### 9.3 Principe

Chaque modèle est confronté à une **valeur analytique indépendante** (formule fermée,
moment théorique, propriété mathématique), jamais à une valeur recopiée de sa propre
sortie. Pour les simulations, la tolérance est fixée en multiples de l'erreur
standard Monte Carlo.

### 9.4 Vérifications manuelles effectuées

- Les sept écrans, pilotés dans Chrome sur les données réelles, à 1 440 px et 390 px
  de large.
- Les indicateurs du tableau de bord sont identiques à ceux de `/trading/risk`.
- La migration a été appliquée, annulée, puis réappliquée sur PostgreSQL 16.

---

## 10. Sécurité et isolation des utilisateurs

- Toutes les routes exigent un utilisateur connecté (`get_current_user`, mécanisme
  existant). La saisie des caractéristiques obligataires exige le rôle
  administrateur (`require_admin`).
- Un portefeuille est chargé avec la condition `portfolio.user_id == utilisateur`. Un
  identifiant appartenant à un autre utilisateur renvoie **la même erreur 404**
  qu'un identifiant inexistant, pour ne rien révéler.
- L'historique des calculs est filtré par utilisateur.
- Les tests vérifient l'isolation sur le tableau de bord, le rapport de risque,
  l'optimisation, la liste des portefeuilles et l'historique.
- Les entrées sont bornées par Pydantic (tailles de listes, plages de valeurs), ce
  qui empêche aussi les calculs démesurés (voir [§11](#11-performances-et-limites-de-calcul)).
- Aucun secret dans le code : le module n'utilise aucune variable d'environnement.

---

## 11. Performances et limites de calcul

Les routes sont **synchrones** : FastAPI les exécute dans son pool de threads, donc
un calcul numpy ne bloque pas la boucle d'événements. Les limites ci-dessous bornent
le temps de calcul et la mémoire.

| Calcul | Limite | Temps mesuré (pire cas) |
|---|---|---|
| Simulation stochastique | 20 000 trajectoires, 2 520 pas, produit ≤ 5 040 000 | < 0,5 s (GBM 0,29 s, CIR 0,46 s, Hull-White 0,29 s) |
| Analyse de sensibilité | 2 000 trajectoires × 5 niveaux | inclus ci-dessus |
| Rapport de risque complet (VaR Monte Carlo × 3 horizons) | 50 000 simulations par horizon | 0,1 s avec 10 000 simulations (valeur par défaut) |
| Optimisation | 25 points de frontière (60 au plus) | ≈ 0,2 s |
| Perte annuelle | 200 000 années, 10 millions de pertes tirées au plus ; scénarios de stress plafonnés à 50 000 années | 0,4 s (200 000 années) |
| Laboratoire | 6 configurations | somme des calculs |

---

## 12. Limites connues et points d'attention

1. **Historique court.** L'import Twelve Data couvre environ un an (250 jours). Les
   rendements espérés (GBM, Markowitz) et les queues de distribution sont donc
   estimés avec une forte incertitude ; les écrans l'affichent.
2. **Pas de données de taux.** Aucune courbe ni série de taux n'est stockée : taux
   sans risque, courbe initiale de Hull-White et paramètres de Vasicek et CIR sont
   des hypothèses ou proviennent de séries fournies par l'utilisateur.
3. **ETF obligataires.** TLT, SHY, LQD et HYG n'ont pas de caractéristiques
   contractuelles. Les calculs contractuels portent sur des obligations théoriques
   ou sur des lignes `bond_terms` saisies par un administrateur.
4. **`coupon_payments` vide.** Le service existant de coupons
   (`services/bond_service.py`) crédite le cash sans écrire dans cette table. Le
   module la lit correctement, mais elle reste vide tant que ce service n'est pas
   modifié (hors du périmètre de l'Actuariat).
5. **Composition constante.** Toutes les mesures historiques supposent que la
   composition actuelle a été détenue sur toute la période, comme l'écran
   Portefeuille.
6. **Indépendance des événements de perte.** Le regroupement de la volatilité
   (crises) n'est pas modélisé.
7. **Deux conventions de VaR** coexistent (écran Portefeuille et Actuariat ; voir
   [§4.4](#44-quantiles-var-et-expected-shortfall)).
8. **Débordement mobile existant.** À 390 px, toutes les pages de l'application
   (Portefeuille et Analyse compris) font 450 px de large, à cause de la barre
   supérieure partagée. Ce défaut ne vient pas du module.

---

## 13. Étendre le module

### 13.1 Ajouter un modèle au laboratoire

1. Écrire la fonction mathématique dans le sous-dossier adapté (fonction pure,
   tableaux numpy, `ValueError` explicite en français sur une entrée invalide).
2. L'ajouter dans `lab_service.CATALOG` : `family`, `label`, `target`, `formula`,
   `assumptions`, `params`.
3. Brancher son exécution dans `lab_service.run` (ou dans la fonction de sa famille),
   en renvoyant la structure uniforme : `metrics`, `histogram`, `data_source`,
   `params_used`.
4. Si la famille est nouvelle : l'ajouter au `Literal` de `LabModelOut.family`
   (`schemas.py`) et à `FAMILIES` dans `ModelLabPage.jsx`.
5. Tests : une valeur analytique dans un fichier unitaire, et un appel
   `/lab/run` dans les tests d'API.

L'écran du laboratoire n'a pas besoin d'être modifié : il lit le catalogue.

### 13.2 Ajouter une route

Suivre le modèle de `api.py` :

- schémas d'entrée et de sortie dans `schemas.py` ;
- `Depends(get_current_user)` ;
- calcul dans un bloc `with _http_errors():` (`LookupError` → 404,
  `ValueError` → 422) ;
- `record_run(...)` si le calcul doit apparaître dans l'historique.

### 13.3 Règles à respecter

- Ne jamais présenter une donnée synthétique ou une hypothèse comme réelle : renseigner
  `data_source`.
- Toute simulation accepte une graine.
- Documenter formule, hypothèses et conventions dans la docstring du module et dans
  le panneau « Conventions » de l'écran.
- Ne modifier aucun fichier d'un autre module sans accord de son auteur.

---

## 14. Reste à faire

| Sujet | Détail |
|---|---|
| Stress testing bancaire | La table `banks` existe (6 banques synthétiques), mais aucun moteur de stress n'a été développé dans le projet. Prévu : exposer les fonctions de choc et de capital du module (chocs de marché, de taux, de volatilité, VaR/ES sous stress) pour le module Stress Testing, sans construire ce module à la place de son responsable. |
| Validation Docker | Reconstruire l'image backend, installer `recharts` dans le conteneur frontend, appliquer la migration et lancer la suite de tests dans Docker. |
| Commits | Le travail est sur la branche `feature/actuariat`, pas encore commité (identité git à configurer sur le poste de développement). |
| Lien depuis le README | Ajouter un renvoi vers cette documentation dans la section « État du projet » du README. |

---

## 15. Glossaire

| Terme | Définition |
|---|---|
| **VaR** (Value at Risk) | Perte qui n'est dépassée qu'avec une probabilité 1 − α sur l'horizon choisi |
| **Expected Shortfall** (ES, CVaR, TVaR) | Perte moyenne dans les cas où la VaR est dépassée |
| **Drawdown maximal** | Plus forte baisse entre un sommet et le creux qui suit |
| **Ratio de Sharpe** | Rendement excédentaire par unité de volatilité |
| **Ratio de Sortino** | Rendement excédentaire par unité de volatilité baissière |
| **Backtesting** | Vérification a posteriori qu'un modèle de VaR est dépassé aussi souvent que prévu |
| **GBM** | Mouvement brownien géométrique, modèle standard de prix d'actif |
| **Retour à la moyenne** | Tendance d'un taux à revenir vers un niveau de long terme (paramètre a) |
| **Condition de Feller** | 2ab ≥ σ² : garantit un taux CIR strictement positif |
| **YTM** | Rendement actuariel : taux qui égalise prix et valeur actuelle des flux |
| **Duration** | Maturité moyenne pondérée des flux ; mesure la sensibilité du prix aux taux |
| **Convexité** | Courbure de la relation prix-rendement |
| **DV01** | Variation de prix pour une hausse de taux d'un point de base (0,01 %) |
| **Point de base (pb)** | 0,01 % |
| **Frontière efficiente** | Ensemble des portefeuilles de risque minimal pour chaque niveau de rendement |
| **Fréquence / sévérité** | Nombre de pertes sur une période / montant de chaque perte |
| **Surdispersion** | Variance du nombre de pertes supérieure à sa moyenne (justifie la binomiale négative) |
| **AIC** | Critère d'Akaike : compare des lois ajustées, plus petit = meilleur |
| **Capital économique** | Fonds propres nécessaires pour absorber la perte inattendue à un niveau de confiance donné |
| **Graine (seed)** | Nombre qui initialise le générateur aléatoire et rend une simulation reproductible |
