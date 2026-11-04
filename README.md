# Simulateur de Salle de Marché --- `projet_5infini_violet`

Projet universitaire mené par une équipe de 6 étudiants. L'application
simule une salle de marché pédagogique : cotations réelles, portefeuille
virtuel, ordres d'achat et de vente, suivi du risque et, dans les
prochaines étapes, modules d'analyse, d'intelligence artificielle et de
stress testing bancaire.

Ce README explique comment installer et lancer le projet sur une machine
avec Docker, puis comment contribuer sans perturber le travail des
autres membres.

> Rédigé par Emna --- rôle : gestion de projet et documentation.

------------------------------------------------------------------------

## 1. Stack technique

  -----------------------------------------------------------------------
  Couche                              Technologie
  ----------------------------------- -----------------------------------
  Backend                             Python 3.12 · FastAPI · Uvicorn
                                      (port `8000`)

  Frontend                            React 18 · Vite (port `3000`)

  Base de données                     PostgreSQL 16 (base `salle_marche`)
                                      · SQLAlchemy · Alembic

  Cache                               Redis 7 (cache des cotations et
                                      sessions)

  Données de marché                   API Twelve Data (offre gratuite : 8
                                      requêtes/minute, 800/jour)

  Orchestration                       Docker Compose
  -----------------------------------------------------------------------

## 2. Prérequis

À installer une seule fois :

-   **Docker Desktop** :
    <https://www.docker.com/products/docker-desktop/>
-   **Git** : <https://git-scm.com/downloads>
-   **Visual Studio Code** (recommandé) :
    <https://code.visualstudio.com/>
-   **Un compte GitHub** : transmettre votre nom d'utilisateur à Sarra
    pour être ajouté au dépôt privé.

> **Important :** Docker est nécessaire pour exécuter le projet. Il
> n'est pas nécessaire d'installer Python, Node.js ou PostgreSQL
> séparément : ces dépendances sont exécutées dans les conteneurs.

Sous Windows, redémarrer l'ordinateur si Docker Desktop le demande, puis
ouvrir Docker Desktop et le laisser fonctionner en arrière-plan.

## 3. Installation et premier lancement

Ouvrir un terminal dans le dossier où vous souhaitez placer le projet.

### 3.1 Cloner le dépôt

``` bash
git clone https://github.com/SARRA1920/-projet_5infini_violet.git
cd -projet_5infini_violet
```

### 3.2 Créer le fichier de configuration local

Sous Windows (CMD) :

``` cmd
copy .env.example .env
```

Sous macOS ou Linux :

``` bash
cp .env.example .env
```

Modifier ensuite le fichier `.env` en suivant la section [4.
Configuration du fichier `.env`](#4-configuration-du-fichier-env).

### 3.3 Construire et démarrer les services

Vérifier que Docker Desktop est ouvert, puis exécuter :

``` bash
docker compose up -d --build
```

La première construction peut prendre quelques minutes : Docker
télécharge les images et installe les dépendances Python et Node.js. Les
lancements suivants sont généralement plus rapides.

### 3.4 Initialisation après le premier lancement

Appliquer les migrations de la base de données :

``` bash
docker compose exec backend alembic upgrade head
```

Charger les données initiales (banques, utilisateurs de test et 31
actifs) :

``` bash
docker compose exec backend python -m app.seed
```

Importer environ un an d'historique de cours via Twelve Data (optionnel,
mais recommandé) :

``` bash
docker compose exec backend python -m app.import_prices
```

Cette dernière étape nécessite une clé `TWELVEDATA_API_KEY` dans le
fichier `.env`. Avec l'offre gratuite, l'import peut prendre plusieurs
minutes en raison de la limite de requêtes.

### 3.5 Vérifier le fonctionnement

  -----------------------------------------------------------------------
  Adresse                             Résultat attendu
  ----------------------------------- -----------------------------------
  <http://localhost:3000>             Frontend --- bandeau vert « Statut
                                      du backend : ok »

  <http://localhost:8000/docs>        Documentation interactive Swagger
                                      de l'API

  <http://localhost:8000/health>      Réponse JSON : `{"status":"ok"}`
  -----------------------------------------------------------------------

## 4. Configuration du fichier `.env`

Le fichier `.env.example` sert de modèle. Copier ce fichier vers `.env`,
puis renseigner les valeurs locales.

**Ne jamais commiter le fichier `.env`** : il contient des paramètres
locaux et des secrets. Il est déjà prévu pour être ignoré par
`.gitignore`.

Exemple de configuration :

``` dotenv
# --- Base de données ---
# Choisir un utilisateur et un mot de passe locaux.
# Utiliser les mêmes identifiants dans DATABASE_URL.
# Éviter les caractères spéciaux @ : / % dans le mot de passe.

POSTGRES_USER=emna
POSTGRES_PASSWORD=monmdplocal123

# URLs utilisées lorsque le backend est lancé hors Docker.
# Dans Docker Compose, les hôtes db et redis sont configurés automatiquement.
DATABASE_URL=postgresql://emna:monmdplocal123@localhost:5432/salle_marche
REDIS_URL=redis://localhost:6379/0

# --- Sécurité ---
# Secret aléatoire utilisé pour signer les jetons JWT.
JWT_SECRET=

# Mot de passe des comptes de démonstration.
# Il est lu depuis l'environnement et n'est pas codé en dur.
SEED_PASSWORD=

# --- Données de marché ---
# Clé API Twelve Data : https://twelvedata.com
TWELVEDATA_API_KEY=
```

Les identifiants ci-dessus sont des exemples : chaque membre doit
utiliser ses propres valeurs locales. Si les identifiants PostgreSQL
sont modifiés, mettre à jour `DATABASE_URL` avec les mêmes valeurs.

### Générer un `JWT_SECRET`

Exécuter la commande suivante :

``` bash
docker compose exec backend python -c "import secrets; print(secrets.token_hex(32))"
```

Copier la valeur générée dans `.env` après `JWT_SECRET=`, puis
redémarrer le backend :

``` bash
docker compose restart backend
```

## 5. Architecture du dépôt

``` text
projet_5infini_violet/
├── docker-compose.yml          # Orchestre les 4 services
├── .env.example                # Modèle de configuration
├── README.md                   # Documentation du projet
├── CONTRIBUTING.md             # Conventions de code, branches, commits et PR
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/           # Migrations Alembic
│   └── app/
│       ├── main.py             # Point d’entrée FastAPI
│       ├── seed.py             # Données initiales (idempotent)
│       ├── import_prices.py    # Import Twelve Data vers price_history
│       ├── market_data.py      # Client Twelve Data avec limitation de débit
│       ├── pay_coupons.py      # Versement journalier des coupons obligataires
│       ├── api/                # Routes FastAPI (authentification, cotations, trading)
│       ├── models/             # Modèles SQLAlchemy
│       ├── schemas/             # Schémas Pydantic et validation
│       ├── services/           # Logique métier
│       └── core/               # Base de données et sécurité
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    └── src/
        ├── App.jsx             # Routage React Router
        ├── main.jsx
        ├── pages/              # Login, Register, Dashboard, Markets, Trading, Portfolio…
        ├── components/         # AppShell, ProtectedRoute, GuestRoute, AuthLayout
        ├── services/           # Client API et fonctions de formatage
        └── context/            # AuthContext.jsx
```

### Les quatre services Docker

  ---------------------------------------------------------------------------
  Service          Image /                             Port Rôle
                   construction                             
  ---------------- ------------------ --------------------- -----------------
  `db`             `postgres:16`                     `5432` Base
                                                            `salle_marche`,
                                                            données
                                                            persistées dans
                                                            le volume
                                                            `pgdata`

  `redis`          `redis:7-alpine`                  `6379` Cache des
                                                            cotations et
                                                            sessions

  `backend`        Construction                      `8000` API FastAPI et
                   locale                                   documentation sur
                                                            `/docs`

  `frontend`       Construction                      `3000` Application
                   locale                                   React/Vite
  ---------------------------------------------------------------------------

## 6. Modèle de données

Les tables principales sont gérées par Alembic.

  -----------------------------------------------------------------------
  Table                               Contenu
  ----------------------------------- -----------------------------------
  `users`                             Adresse e-mail, nom d'utilisateur,
                                      mot de passe haché avec Argon2 et
                                      rôle (`user` / `admin`)

  `assets`                            31 actifs : actions, ETF, devises,
                                      matières premières et obligations

  `price_history`                     Cours journaliers OHLCV par actif
                                      (unicité `asset_id` + date)

  `portfolios`                        Un portefeuille par utilisateur,
                                      avec un solde initial de 100 000 €

  `positions`                         Quantité détenue et prix moyen
                                      pondéré par actif et portefeuille

  `transactions`                      Historique des ordres (`BUY` /
                                      `SELL`), prix, stop-loss et
                                      take-profit

  `coupon_payments`                   Coupons obligataires, avec au plus
                                      un versement par position et par
                                      jour

  `banks`                             Banques synthétiques destinées au
                                      module de stress testing
  -----------------------------------------------------------------------

### Règles métier déjà implémentées

-   Authentification par JWT (HS256).
-   Mots de passe hachés avec Argon2.
-   Achat et vente avec calcul du prix moyen pondéré.
-   Vente à découvert interdite.
-   Verrouillage pessimiste du portefeuille et transaction unique par
    ordre.
-   Coupons obligataires simulés à 4 % par an, avec mécanisme idempotent
    et contrainte d'unicité.
-   `stop_loss` et `take_profit` enregistrés sur les transactions ; leur
    exécution automatique est prévue dans une étape ultérieure.

## 7. Commandes utiles au quotidien

### Consulter les logs

``` bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs db
```

### Redémarrer le backend après une modification de configuration

``` bash
docker compose restart backend
```

### Arrêter les conteneurs sans supprimer les données

``` bash
docker compose stop
```

### Tout arrêter et supprimer les volumes

``` bash
docker compose down -v
```

> **Attention :** `docker compose down -v` supprime les volumes, y
> compris les données de la base PostgreSQL locale.

### Appliquer les migrations après un `git pull`

``` bash
docker compose exec backend alembic upgrade head
```

### Recharger les données initiales

``` bash
docker compose exec backend python -m app.seed
```

Le seed est conçu pour être idempotent : il ne doit pas dupliquer les
données lorsqu'il est relancé.

### Réimporter les cours de marché

``` bash
docker compose exec backend python -m app.import_prices
```

### Accéder au shell PostgreSQL

``` bash
docker compose exec db psql -U emna -d salle_marche
```

Remplacer `emna` par la valeur de `POSTGRES_USER` définie dans votre
fichier `.env`.

## 8. Dépannage

  -----------------------------------------------------------------------
  Problème                            Solution
  ----------------------------------- -----------------------------------
  `docker` n'est pas reconnu          Fermer puis rouvrir le terminal et
                                      vérifier que Docker Desktop est
                                      démarré.

  Le port `5432` est déjà utilisé     Un serveur PostgreSQL local utilise
                                      probablement ce port. L'arrêter ou
                                      modifier le port exposé dans
                                      `docker-compose.yml`.

  Le port `3000` ou `8000` est déjà   Arrêter l'application qui utilise
  utilisé                             le port ou modifier le mapping dans
                                      `docker-compose.yml`.

  Le frontend indique que le backend  Attendre quelques secondes et
  est injoignable                     actualiser la page. Si le problème
                                      persiste, consulter
                                      `docker compose logs backend`.

  `alembic upgrade head` échoue       Vérifier avec `docker compose ps`
                                      que le service `db` est démarré et
                                      prêt.

  `TWELVEDATA_API_KEY` est vide       Ajouter la clé dans `.env`, puis
                                      redémarrer le backend.

  L'import des prix est lent          C'est attendu avec la limite de
                                      l'offre gratuite de Twelve Data.

  Certains symboles n'ont pas de      Certains symboles peuvent ne pas
  cours                               être disponibles avec l'offre ou le
                                      marché pris en charge. Consulter
                                      les messages de fin d'import.
  -----------------------------------------------------------------------

## 9. Workflow Git --- travail en équipe

Cette section présente les règles essentielles. Les détails sont
disponibles dans `CONTRIBUTING.md`.

1.  Ne jamais travailler directement sur la branche `main`.

2.  Créer une branche par fonctionnalité, par exemple :

    ``` bash
    git checkout -b feature/nom-du-module
    ```

3.  Récupérer les dernières modifications avant de commencer :

    ``` bash
    git pull
    ```

4.  Envoyer les modifications sur sa branche, puis ouvrir une **Pull
    Request**.

5.  Faire relire la Pull Request par un autre membre avant son
    intégration dans `main`.

6.  Ne pas créer de migration Alembic sans prévenir Sarra : les
    migrations doivent conserver une chaîne cohérente avec un seul
    `head`.

Consulter `CONTRIBUTING.md` avant toute contribution pour connaître les
conventions détaillées.

## 10. État du projet

### Sprint 0 --- Terminé

-   Infrastructure Docker et base de données.
-   Données initiales (*seed*).
-   Authentification backend et frontend.
-   Intégration des données de marché via Twelve Data.
-   Trading et gestion du portefeuille.
-   Obligations et coupons.
-   Extension internationale avec 15 actifs supplémentaires.

### Sprint 1 --- En cours

-   Indicateurs de risque.
-   Tests du trading et des coupons.
-   Page d'administration.
-   Exécution automatique des stop-loss et take-profit.
-   Exploration des données `price_history` à l'aide d'un notebook.

Consulter le board de suivi (Trello ou GitHub Projects) pour connaître
l'affectation détaillée des tâches.

## 11. Licences et données

-   **Code :** usage pédagogique dans le cadre d'un projet
    universitaire.
-   **Données de marché :** fournies par Twelve Data et soumises aux
    conditions de son offre gratuite, notamment en matière d'utilisation
    et de marchés accessibles.
-   **Données personnelles :** le projet utilise des comptes de
    démonstration créés par le seed ; aucune donnée personnelle réelle
    n'est prévue dans le jeu de données de démonstration.

------------------------------------------------------------------------

Pour toute question liée à l'installation ou à la contribution,
consulter `CONTRIBUTING.md` ou contacter l'équipe du projet.
