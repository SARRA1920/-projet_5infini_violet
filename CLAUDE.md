# Simulateur de Salle de Marché

Projet universitaire mené par une équipe de 6.

## Stack
- **Backend** : Python + FastAPI
- **Frontend** : React
- **Base de données** : PostgreSQL + SQLAlchemy + Alembic (migrations)
- **Cache / temps réel** : Redis
- **Orchestration** : Docker Compose

## Modules
1. Trading et portefeuille virtuel
2. Gestion du risque
3. Analyse financière
4. Formation
5. IA : prédiction, agent de trading, analyse de sentiment
6. Stress testing bancaire avec XAI (SHAP)
7. Actuariat

## Structure
```
backend/app/
  api/        # routes FastAPI
  models/     # modèles SQLAlchemy
  schemas/    # schémas Pydantic
  services/   # logique métier
  core/       # configuration, sécurité, connexion BD
frontend/src/
  components/ pages/ services/ hooks/
docker-compose.yml   # backend, frontend, db (PostgreSQL 16, base salle_marche), redis
```

## Conventions
- Code et commentaires en français **ou** en anglais, mais cohérents au sein d'un même module.
- Un module par branche Git.
- Secrets uniquement via variables d'environnement (fichier `.env` non commité) — jamais en dur dans le code ni dans `docker-compose.yml`.
