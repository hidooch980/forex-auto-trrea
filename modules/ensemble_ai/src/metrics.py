import numpy as np
from sklearn.metrics import accuracy_score, log_loss, confusion_matrix

def expected_calibration_error(y, p, bins=10):
    conf = p.max(axis=1); pred = p.argmax(axis=1)
    ece = 0.0
    for lo, hi in zip(np.linspace(0,1,bins+1)[:-1], np.linspace(0,1,bins+1)[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            ece += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(ece)

def report(y, p):
    return {
        "samples": int(len(y)),
        "accuracy": float(accuracy_score(y,p.argmax(axis=1))),
        "log_loss": float(log_loss(y,p,labels=[0,1,2])),
        "ece": expected_calibration_error(y,p),
        "confusion_matrix": confusion_matrix(y,p.argmax(axis=1),labels=[0,1,2]).tolist()
    }
