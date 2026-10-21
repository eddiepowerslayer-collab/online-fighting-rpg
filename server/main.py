"""Run the LAN game server:  python -m server.main  [--host 0.0.0.0] [--port 5555] [--db PATH]"""
import argparse
import asyncio
import logging
import os
import socket

from server.game_server import GameServer
from shared import modes as M
from shared.protocol import DEFAULT_PORT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lan_ip() -> str:
    """Best-guess LAN address (no packets are actually sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


async def amain(args):
    server = GameServer(args.db, args.host, args.port, args.allow_small_matches)
    await server.start()
    print(f"Game server running. Players on your network connect to  {lan_ip()}:{server.port}")
    print(f"Database: {os.path.abspath(args.db)}   (Ctrl+C to stop)")
    try:
        await asyncio.Event().wait()
    finally:
        await server.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = reachable from your LAN; 127.0.0.1 = this PC only")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--db", default=os.environ.get("RPG_DB_PATH", os.path.join(ROOT, "saves", "game.db")))
    ap.add_argument("--allow-small-matches", action="store_true",
                    help="TESTING: start team modes with 1 per team and co-op with 1 player")
    ap.add_argument("--backup-on-start", action="store_true", help="copy the database to saves/backups first")
    ap.add_argument("--time-limit", type=float, help="match time limit in seconds (default 180)")
    ap.add_argument("--kill-limit", type=int, help="kills needed to win (overrides each mode's default)")
    ap.add_argument("--respawn", type=float, help="respawn delay in seconds (default 3)")
    args = ap.parse_args()
    M.configure(args.time_limit, args.kill_limit, args.respawn)
    if args.backup_on_start and os.path.exists(args.db):
        from server.backup import backup_database
        print("Backup written to", backup_database(args.db, os.path.join(os.path.dirname(args.db), "backups")))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
