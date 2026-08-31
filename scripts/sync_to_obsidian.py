#!/usr/bin/env python3
"""
sync_to_obsidian.py — Export Aurora KG into an Obsidian vault inside this project.

Usage (from the project root):
    conda activate aurora
    python sync_to_obsidian.py

Vault location:  aurora-final/obsidian-vault/
Open it once in Obsidian as a vault, then this script refreshes it automatically.
"""

import os
import io
import sys
import zipfile
import subprocess
import getpass
import requests
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()   # aurora-final/
VAULT_DIR    = PROJECT_ROOT / "obsidian-KG-vault"       # aurora-final/obsidian-KG-vault/

load_dotenv(PROJECT_ROOT / ".env")

API_BASE = os.getenv("AURORA_API_BASE", "http://localhost:8000/api")


# ── Auth ───────────────────────────────────────────────────────────────────────
def login() -> str:
    username = os.getenv("AURORA_USERNAME", "")
    password = os.getenv("AURORA_PASSWORD", "")
    if not username:
        username = input("Aurora username: ").strip()
    if not password:
        password = getpass.getpass("Aurora password: ")

    r = requests.post(f"{API_BASE}/auth/login",
                      json={"username": username, "password": password}, timeout=10)
    if r.status_code != 200:
        print(f"❌ Login failed: {r.json().get('detail', r.text)}")
        sys.exit(1)
    print(f"✅ Logged in as {username}")
    return r.json()["access_token"]


# ── Export ─────────────────────────────────────────────────────────────────────
def export_kg(token: str) -> bytes:
    print("📦 Fetching Knowledge Graph...")
    r = requests.get(f"{API_BASE}/kg/export/obsidian",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code != 200:
        print(f"❌ Export failed: {r.status_code}")
        sys.exit(1)
    return r.content


# ── Write vault ────────────────────────────────────────────────────────────────
def write_to_vault(zip_bytes: bytes) -> list:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            # Strip the leading "Aurora KG/" prefix
            parts = Path(name).parts
            dest  = VAULT_DIR / Path(*parts[1:]) if len(parts) > 1 else VAULT_DIR / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            written.append(dest.relative_to(VAULT_DIR))
    return written


# ── Open Obsidian ──────────────────────────────────────────────────────────────
def open_obsidian():
    vault_name = VAULT_DIR.name   # "obsidian-vault"
    vault_uri  = f"obsidian://open?vault={requests.utils.quote(vault_name)}"

    result = subprocess.run(["open", vault_uri], capture_output=True)

    if result.returncode != 0:
        # Vault not registered yet — open Obsidian and show one-time instructions
        subprocess.run(["open", "-a", "Obsidian"], capture_output=True)
        print()
        print("=" * 54)
        print("  ⚡ One-time setup — do this once, never again")
        print("=" * 54)
        print()
        print("  Obsidian is open. Now:")
        print()
        print("  1. Click  'Open folder as vault'")
        print(f"  2. Navigate to this project folder:")
        print(f"     {PROJECT_ROOT}")
        print(f"  3. Select the  obsidian-KG-vault  folder inside it")
        print("  4. Click  Open")
        print("  5. Press  Cmd+G  →  Graph View")
        print()
        print("  Next time: script opens Obsidian automatically ✅")
        print("=" * 54)
    else:
        print("🚀 Obsidian opened → press Cmd+G for Graph View")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  Aurora → Obsidian KG Sync")
    print("=" * 50)

    # Check server
    try:
        requests.get(f"{API_BASE.replace('/api','')}/api/health", timeout=3)
    except Exception:
        print(f"❌ Server not running at {API_BASE}")
        print("   Start it: conda activate aurora && uvicorn app:app --reload --port 8000")
        sys.exit(1)

    token    = login()
    zip_data = export_kg(token)
    files    = write_to_vault(zip_data)

    print(f"✅ {len(files)} files written to:  {VAULT_DIR}")
    print()
    for f in sorted(files):
        print(f"   {f}")
    print()

    open_obsidian()
    print()
    print("💡 Re-run anytime after chatting to refresh the graph.")


if __name__ == "__main__":
    main()
