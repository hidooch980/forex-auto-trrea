import numpy as np

def soft_vote(probabilities, weights=(1/3,1/3,1/3)):
    """Inputs are arrays [n,3] in fixed class order down/flat/up."""
    if len(probabilities) != 3:
        raise ValueError("Expected MLP, LSTM and XGBoost probabilities")
    w = np.asarray(weights, dtype=float)
    if np.any(w < 0) or not np.isclose(w.sum(), 1):
        raise ValueError("Weights must be non-negative and sum to one")
    p = sum(wi*np.asarray(pi) for wi,pi in zip(w, probabilities))
    p = np.clip(p, 1e-9, 1)
    return p / p.sum(axis=1, keepdims=True)

def choose_weights(y, prob_list):
    """Small validation-only grid; never use test/holdout data here."""
    best, best_loss = (1/3,1/3,1/3), float("inf")
    candidates = [(a,b,1-a-b) for a in (0.2,0.4,0.6)
                  for b in (0.2,0.4,0.6) if 1-a-b >= 0.1]
    for w in candidates:
        p = soft_vote(prob_list, w)
        loss = -np.log(np.clip(p[np.arange(len(y)), y],1e-9,1)).mean()
        if loss < best_loss:
            best, best_loss = w, loss
    return best
