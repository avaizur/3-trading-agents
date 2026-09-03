def expectancy(win_rate: float, average_win: float, average_loss: float) -> float:
    return (win_rate * average_win) - ((1 - win_rate) * abs(average_loss))

def profit_factor(gross_profit: float, gross_loss: float) -> float:
    loss = abs(gross_loss)
    if loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / loss
