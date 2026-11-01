import argparse, json
from pathlib import Path
import joblib, numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from .data import load_frame, make_features, make_labels
from .models import build_mlp, build_xgb, build_lstm, sequences
from .ensemble import choose_weights, soft_vote
from .metrics import report
from .registry import write_manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv",required=True); ap.add_argument("--out",default="artifacts")
    args=ap.parse_args()
    df=load_frame(args.csv); X=make_features(df); y=make_labels(df)
    valid=y.notna() & X.notna().all(axis=1)
    X=X.loc[valid].reset_index(drop=True); y=y.loc[valid].to_numpy()
    if len(X)<1500: raise ValueError("Need >=1500 clean rows for this starter workflow")
    # Chronological train/validation/holdout; holdout is never used for fitting/weights.
    n=len(X); a=int(n*.70); b=int(n*.85)
    xtr,xv,xte=X.iloc[:a],X.iloc[a:b],X.iloc[b:]
    ytr,yv,yte=y[:a],y[a:b],y[b:]
    mlp=build_mlp().fit(xtr,ytr)
    xgb=build_xgb().fit(xtr,ytr)
    # LSTM uses train-only imputer/scaler; validation/holdout transformed with same fit.
    imp=SimpleImputer(strategy="median"); sc=StandardScaler()
    ztr=sc.fit_transform(imp.fit_transform(xtr))
    zall=sc.transform(imp.transform(X))
    seq_x,seq_y,idx=sequences(zall,y,64)
    trmask=idx<a; vmask=(idx>=a)&(idx<b); temask=idx>=b
    lstm=build_lstm(64,ztr.shape[1])
    lstm.fit(seq_x[trmask],seq_y[trmask],epochs=25,batch_size=64,
             validation_data=(seq_x[vmask],seq_y[vmask]),callbacks=[
                 __import__("tensorflow").keras.callbacks.EarlyStopping(
                   patience=4,restore_best_weights=True)],verbose=0)
    # Align tree/MLP validation predictions to sequence end indices.
    val_idx=idx[vmask]; test_idx=idx[temask]
    p_val=[mlp.predict_proba(X.iloc[val_idx]), lstm.predict(seq_x[vmask],verbose=0),
           xgb.predict_proba(X.iloc[val_idx])]
    weights=choose_weights(y[val_idx],p_val)
    p_test=[mlp.predict_proba(X.iloc[test_idx]),lstm.predict(seq_x[temask],verbose=0),
            xgb.predict_proba(X.iloc[test_idx])]
    p=soft_vote(p_test,weights); metrics=report(y[test_idx],p)
    out=Path(args.out)/"candidate"; out.mkdir(parents=True,exist_ok=True)
    joblib.dump(mlp,out/"mlp.joblib"); joblib.dump(xgb,out/"xgb.joblib")
    joblib.dump(imp,out/"imputer.joblib"); joblib.dump(sc,out/"scaler.joblib")
    lstm.save(out/"lstm.keras")
    write_manifest(out,metrics,X.columns.tolist(),weights)
    print(json.dumps(metrics,indent=2))
if __name__=="__main__": main()
