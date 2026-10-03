"""Trained guardrail models live in a GitHub release (too big for git) and are fetched on demand.

    python -m guardrails.model_store            # the default model from policy.toml
    python -m guardrails.model_store --all      # every model, for the comparison experiments
    python -m guardrails.model_store --pack     # maintainers: zip models/ and rewrite the manifest

The pipeline calls ensure_model() itself, so a fresh clone downloads the default model
on first use. Every file is checked against the SHA-256 pinned in models_manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).with_name("models_manifest.json")
PACK_DIR = ROOT / "models" / "_release"


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"release_url": "", "models": {}}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ensure_model(rel_path: str, quiet: bool = False) -> bool:
    """Make sure models/<name> exists locally, downloading it if the manifest has it."""
    target = ROOT / rel_path
    if target.exists():
        return True
    manifest = load_manifest()
    entry = manifest["models"].get(target.name)
    if not entry or not manifest.get("release_url"):
        return False
    url = f"{manifest['release_url']}/{entry['asset']}"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        download = Path(tmp) / entry["asset"]
        if not quiet:
            print(f"downloading {entry['asset']} ({entry['size'] / 1e6:.0f} MB) ...", file=sys.stderr, flush=True)
        try:
            with urllib.request.urlopen(url, timeout=60) as resp, open(download, "wb") as out:
                shutil.copyfileobj(resp, out, 1 << 20)
        except OSError as exc:
            print(f"could not download {url}: {exc}", file=sys.stderr)
            return False
        if _sha256(download) != entry["sha256"]:
            print(f"checksum mismatch for {entry['asset']}, not installing it", file=sys.stderr)
            return False
        if entry["asset"].endswith(".zip"):
            with zipfile.ZipFile(download) as zf:
                zf.extractall(Path(tmp) / "unpacked")
            (Path(tmp) / "unpacked" / target.name).replace(target)
        else:
            download.replace(target)
    return True


def pack(release_url: str) -> None:
    """Zip each model under models/ into models/_release and write the manifest."""
    PACK_DIR.mkdir(parents=True, exist_ok=True)
    models = {}
    for item in sorted((ROOT / "models").iterdir()):
        if item.name.startswith("_"):
            continue
        if item.is_dir():
            asset = PACK_DIR / f"{item.name}.zip"
            with zipfile.ZipFile(asset, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
                for f in sorted(item.rglob("*")):
                    if f.is_file():
                        zf.write(f, Path(item.name) / f.relative_to(item))
        else:
            asset = PACK_DIR / item.name
            shutil.copyfile(item, asset)
        models[item.name] = {"asset": asset.name, "sha256": _sha256(asset), "size": asset.stat().st_size}
        print(f"packed {asset.name} {asset.stat().st_size / 1e6:.0f} MB")
    MANIFEST_PATH.write_text(json.dumps({"release_url": release_url, "models": models}, indent=2) + "\n",
                             encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*", help="model names from the manifest; default: the model in policy.toml")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pack", metavar="RELEASE_URL", help="zip local models and write the manifest")
    args = ap.parse_args()
    if args.pack:
        pack(args.pack)
        return
    manifest = load_manifest()
    if args.all:
        names = list(manifest["models"])
    elif args.names:
        names = args.names
    else:
        from .policy import load_config

        cfg = load_config()["classifier"]
        names = [Path(cfg["model_dir"]).name, Path(cfg["tfidf_path"]).name]
    for name in names:
        ok = ensure_model(f"models/{name}")
        print(f"{'ok     ' if ok else 'MISSING'} models/{name}")


if __name__ == "__main__":
    main()
