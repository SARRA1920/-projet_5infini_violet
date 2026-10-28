"""Indicateurs d'analyse technique, calculés sur des listes de cours de clôture."""


def sma(values: list[float], window: int) -> list[float | None]:
    """Moyenne mobile simple : moyenne des `window` derniers cours.

    Les `window - 1` premiers jours valent None (pas assez d'historique).
    Exemple : cours 100, 102, 101, 103, 104 avec window=5 -> dernier point = 102.
    """
    result: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= window:
            running -= values[index - window]
        result.append(running / window if index >= window - 1 else None)
    return result


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    """RSI de Wilder : force relative des hausses face aux baisses, entre 0 et 100.

    RSI = 100 - 100 / (1 + gain moyen / perte moyenne). Au-dessus de 70 le cours est
    jugé suracheté, en dessous de 30 survendu. Les `period` premiers jours valent None.
    """
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(c, 0.0) for c in changes[:period]) / period
    loss = sum(max(-c, 0.0) for c in changes[:period]) / period

    def to_rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        return 100 - 100 / (1 + avg_gain / avg_loss)

    result[period] = to_rsi(gain, loss)
    for i in range(period + 1, len(values)):
        change = changes[i - 1]
        gain = (gain * (period - 1) + max(change, 0.0)) / period
        loss = (loss * (period - 1) + max(-change, 0.0)) / period
        result[i] = to_rsi(gain, loss)
    return result
