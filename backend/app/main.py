from fastapi import FastAPI

app = FastAPI(title="Simulateur de Salle de Marché")


@app.get("/health")
def health():
    """Vérifie que l'API répond."""
    return {"status": "ok"}
