import argparse, json
from pathlib import Path
import joblib
import numpy as np
from tensorflow import keras
from .data import load_frame,make_features,make_labels
from .models import sequences
from .ensemble import soft_vote
from .metrics import report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--csv",required=True)
    ap.add_argument("--model-dir",required=True); a=ap.parse_args()
    d=Path(a.model_dir); m=json.loads((d/"manifest.json").read_text())
    df=load_frame(a.csv); X=make_features(df)[m["feature_names"]]; y=make_labels(df)
    valid=y.notna() & X.notna().all(axis=1); X=X.loc[valid].reset_index(drop=True); y=y.loc[valid].to_numpy()
    n=len(X); start=int(n*.85)
    # This evaluates the final 15% only when model was trained on an earlier snapshot.
    if start >= n: raise ValueError("No holdout rows")
    mlp=joblib.load(d/"mlp.joblib"); xgb=joblib.load(d/"xgb.joblib")
    imp=joblib.load(d/"imputer.joblib"); sc=joblib.load(d/"scaler.joblib")
    z=sc.transform(imp.transform(X))
    sx,sy,idx=sequences(z,y,64); mask=idx>=start
    lstm=keras.models.load_model(d/"lstm.keras")
    p=soft_vote([mlp.predict_proba(X.iloc[idx[mask]]),
                 lstm.predict(sx[mask],verbose=0),
                 xgb.predict_proba(X.iloc[idx[mask]])],m["ensemble_weights"])
    print(json.dumps(report(y[idx[mask]],p),indent=2))
if __name__=="__main__": main()
