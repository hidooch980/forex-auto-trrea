import json, os, shutil, tempfile
from pathlib import Path
from datetime import datetime, timezone

def write_manifest(model_dir, metrics, feature_names, weights):
    p = Path(model_dir); p.mkdir(parents=True, exist_ok=True)
    manifest = {
      "created_utc": datetime.now(timezone.utc).isoformat(),
      "metrics": metrics, "feature_names": list(feature_names),
      "class_order": ["down","flat","up"], "ensemble_weights": list(weights)
    }
    (p/"manifest.json").write_text(json.dumps(manifest,indent=2), encoding="utf-8")
    return manifest

def promote(candidate, active):
    """Atomic directory swap on same filesystem; keeps prior active as .previous."""
    candidate, active = Path(candidate), Path(active)
    if not (candidate/"manifest.json").exists():
        raise ValueError("Candidate has no manifest")
    previous = active.with_name(active.name + ".previous")
    if previous.exists(): shutil.rmtree(previous)
    if active.exists(): os.replace(active, previous)
    os.replace(candidate, active)
