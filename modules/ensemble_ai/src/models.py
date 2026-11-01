import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier
import tensorflow as tf
from tensorflow import keras

def build_mlp():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", MLPClassifier(hidden_layer_sizes=(128,64,32,16),
          activation="relu", alpha=1e-4, learning_rate_init=3e-4,
          early_stopping=True, validation_fraction=0.15,
          max_iter=250, random_state=42))
    ])

def build_xgb():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", XGBClassifier(
            n_estimators=500, max_depth=4, learning_rate=0.025,
            subsample=0.8, colsample_bytree=0.8,
            objective="multi:softprob", num_class=3,
            eval_metric="mlogloss", reg_lambda=3,
            random_state=42, n_jobs=4))
    ])

def build_lstm(sequence_length, n_features):
    tf.keras.utils.set_random_seed(42)
    model = keras.Sequential([
        keras.layers.Input(shape=(sequence_length, n_features)),
        keras.layers.LSTM(64, return_sequences=True),
        keras.layers.Dropout(0.25),
        keras.layers.LSTM(32),
        keras.layers.Dense(24, activation="relu"),
        keras.layers.Dropout(0.2),
        keras.layers.Dense(3, activation="softmax")
    ])
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=3e-4),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return model

def sequences(x, y, length=64):
    xs, ys, end_idx = [], [], []
    a = np.asarray(x, dtype="float32")
    b = np.asarray(y, dtype="int64")
    for i in range(length-1, len(a)):
        if np.isfinite(a[i-length+1:i+1]).all():
            xs.append(a[i-length+1:i+1]); ys.append(b[i]); end_idx.append(i)
    return np.asarray(xs), np.asarray(ys), np.asarray(end_idx)
