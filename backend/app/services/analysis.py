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


def backtest_crossover(
    closes: list[float], short_window: int, long_window: int, capital: float = 10000.0
) -> dict | None:
    """Rejoue la stratégie « croisement de moyennes mobiles » sur le passé.

    Règle : on est investi tant que la moyenne courte est au-dessus de la longue, sinon
    on est en liquidités. Le signal observé à la clôture d'un jour s'applique à partir
    de ce jour (achat ou vente au cours de clôture). Aucun frais n'est compté.

    Renvoie None s'il n'y a pas assez de cours pour calculer la moyenne longue.
    La courbe commence le premier jour où les deux moyennes existent ; la comparaison
    « acheter et garder » part du même jour avec le même capital.
    """
    short = sma(closes, short_window)
    long_ = sma(closes, long_window)
    start = long_window - 1
    if len(closes) < start + 2:
        return None

    strategy = [capital]
    buy_hold = [capital]
    invested = False
    entries = 0
    days_invested = 0
    for i in range(start + 1, len(closes)):
        was_invested = short[i - 1] > long_[i - 1]
        if was_invested and not invested:
            entries += 1
        invested = was_invested
        daily = closes[i] / closes[i - 1]
        strategy.append(strategy[-1] * (daily if invested else 1.0))
        buy_hold.append(capital * closes[i] / closes[start])
        days_invested += 1 if invested else 0

    return {
        "start_index": start,
        "strategy": strategy,
        "buy_hold": buy_hold,
        "strategy_return_pct": (strategy[-1] / capital - 1) * 100,
        "buy_hold_return_pct": (buy_hold[-1] / capital - 1) * 100,
        "strategy_max_drawdown_pct": _max_drawdown(strategy),
        "buy_hold_max_drawdown_pct": _max_drawdown(buy_hold),
        "entries": entries,
        "time_in_market_pct": days_invested / (len(strategy) - 1) * 100,
    }
