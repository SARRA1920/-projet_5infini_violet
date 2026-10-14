from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.quotes import router as quotes_router

app = FastAPI(title="Simulateur de Salle de Marché")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(quotes_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    """Vérifie que l'API répond."""
    return {"status": "ok"}
