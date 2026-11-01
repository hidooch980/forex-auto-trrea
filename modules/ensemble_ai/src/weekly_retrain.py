import argparse, json
from pathlib import Path
from .train import main as train_main
# Orchestrator intentionally does not promote automatically.
# Schedule this command weekly; evaluate candidate, inspect gates, then explicitly promote.
def main():
    print("Run: python -m src.train --csv SNAPSHOT.csv --out artifacts")
    print("Then evaluate on an untouched holdout snapshot.")
    print("Promotion is a separate, explicit operation after review.")
if __name__=="__main__": main()
