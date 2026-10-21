"""Back up the game database.   python -m server.backup [--db PATH] [--out DIR] [--keep N]

Uses SQLite's online backup API, so it is safe to run while the server is running and always
produces a consistent copy. To restore: stop the server and copy a backup over saves/game.db."""
import argparse
import os
import sqlite3
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def backup_database(src: str, out_dir: str, keep: int = 10) -> str:
    """Write a timestamped copy of `src` into `out_dir`; prune to the newest `keep` copies."""
    if not os.path.exists(src):
        raise FileNotFoundError(f"No database at {src}")
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, time.strftime("game-%Y%m%d-%H%M%S.db"))
    n = 1
    while os.path.exists(dest):                       # two backups in the same second
        dest = os.path.join(out_dir, time.strftime("game-%Y%m%d-%H%M%S") + f"-{n}.db")
        n += 1
    source = sqlite3.connect(src)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    if keep > 0:
        files = sorted(f for f in os.listdir(out_dir) if f.startswith("game-") and f.endswith(".db"))
        for old in files[:-keep]:
            os.remove(os.path.join(out_dir, old))
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("RPG_DB_PATH", os.path.join(ROOT, "saves", "game.db")))
    ap.add_argument("--out", default=os.path.join(ROOT, "saves", "backups"))
    ap.add_argument("--keep", type=int, default=10, help="how many backups to keep (0 = keep all)")
    args = ap.parse_args()
    print("Backup written to", backup_database(args.db, args.out, args.keep))


if __name__ == "__main__":
    main()
