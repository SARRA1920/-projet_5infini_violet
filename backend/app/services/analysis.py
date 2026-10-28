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


def _max_drawdown(curve: list[float]) -> float:
    """Plus grande chute (en %) entre un sommet de la courbe et le creux qui suit."""
    peak = curve[0]
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        worst = max(worst, 1 - value / peak)
    return worst * 100


# ---- Signaux : True = investi, False = en liquidités, None = indicateur pas encore défini.
# Le signal observé à la clôture du jour i s'applique au rendement du jour i + 1.


def crossover_signal(closes: list[float], short_window: int, long_window: int) -> list[bool | None]:
    """Investi quand la moyenne courte est au-dessus de la moyenne longue."""
    short, long_ = sma(closes, short_window), sma(closes, long_window)
    return [None if a is None or b is None else a > b for a, b in zip(short, long_)]


def trend_signal(closes: list[float], window: int) -> list[bool | None]:
    """Investi quand le cours est au-dessus de sa moyenne mobile."""
    return [None if avg is None else close > avg for close, avg in zip(closes, sma(closes, window))]


def rsi_signal(closes: list[float], period: int = 14, low: float = 30, high: float = 70) -> list[bool | None]:
    """On achète quand le RSI passe sous `low` (survendu), on vend au-dessus de `high`."""
    invested = False
    result: list[bool | None] = []
    for value in rsi(closes, period):
        if value is None:
            result.append(None)
            continue
        if value < low:
            invested = True
        elif value > high:
            invested = False
        result.append(invested)
    return result


def simulate(closes: list[float], signal: list[bool | None], start: int, capital: float = 10000.0) -> dict:
    """Rejoue un signal à partir du jour `start` (même départ pour toutes les stratégies).

    Achat ou vente au cours de clôture, sans frais. Renvoie la courbe de capital
    (une valeur par jour à partir de `start`) et ses indicateurs.
    """
    curve = [capital]
    invested = False
    entries = 0
    days_invested = 0
    for i in range(start + 1, len(closes)):
        now_invested = bool(signal[i - 1])
        if now_invested and not invested:
            entries += 1
        invested = now_invested
        curve.append(curve[-1] * (closes[i] / closes[i - 1] if invested else 1.0))
        days_invested += 1 if invested else 0

    drawdown = _max_drawdown(curve)
    total_return = (curve[-1] / capital - 1) * 100
    days = max(len(curve) - 1, 1)
    return {
        "curve": curve,
        "return_pct": total_return,
        "max_drawdown_pct": drawdown,
        "entries": entries,
        "time_in_market_pct": days_invested / days * 100,
        "return_to_risk": total_return / drawdown if drawdown > 0 else None,
    }
