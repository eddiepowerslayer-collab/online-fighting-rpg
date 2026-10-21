# Online Fighting RPG (Python + Pygame)

A 2D side-scrolling fighting RPG with multiple saved characters, class skills with rebindable
J/K keys, stat allocation, level 1-3000, professions, a player marketplace plus NPC vendors, solo
dungeon runs, and **LAN multiplayer** (1v1, 2v2, 3v3, 4v4, 5v5, Free-For-All and Co-op PvE).

## Quick start

```
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m client.main                  # or press Run on client/main.py in PyCharm
```
Always run from the `online_fighting_rpg` folder.

### Playing alone (works offline)
Click **Host a Game**. This starts the game server on your computer and joins it. Register an
account, create a character and play. No internet is needed.

### Playing with friends on the same Wi-Fi / Ethernet
1. **Host:** click **Host a Game**. The game shows an address such as `192.168.1.23:5555`.
2. **Friends:** on their own computers run the game, type that address into the "Server address"
   box (and the port, default 5555), click **Join Game**, then register their own account.
3. Everyone opens **Arena** and queues for a mode. A match starts when enough players are waiting.

You can also run the server by itself (no game window): `python -m server.main`

### Firewall and network notes
* **Windows:** the first time the server starts, Windows asks to allow Python through the firewall.
  Tick **Private networks** and click Allow. If you missed it: Windows Security > Firewall >
  "Allow an app through firewall" > Python > Private. Or allow TCP port 5555 inbound.
* **macOS:** click Allow when asked to accept incoming connections.
* **Linux:** `sudo ufw allow 5555/tcp`
* **Finding the host's address:** Windows `ipconfig` (IPv4 Address), macOS/Linux `ip addr` or
  `ifconfig`. Addresses like `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x` are private (LAN only).
* **`127.0.0.1` / `localhost` only works on the same computer.** Friends must use the host's LAN address.
* Everyone must be on the same network. Guest Wi-Fi and some school/office networks block
  device-to-device traffic ("client isolation"); then it can't work without a relay/public server.
* No port forwarding or paid hosting is needed for same-network play. Do **not** port-forward this
  server to the internet as-is (see Security).

### Why characters are not saved "on the IP address"
The IP address is only used to *connect*. Your identity is your **account** and your
**character IDs** in the server's database. IP addresses change (Wi-Fi, DHCP, VPN) and are shared
(everyone behind one router looks the same), so saving by IP could hand your character to a stranger
or lose it. Because saves are tied to your account, you can log in from a different computer
(using the host's address) and get the same characters.

## Saves and backups
* Everything permanent (accounts, characters, marketplace, results) lives on the **host** in
  `saves/game.db` (SQLite). Characters are saved automatically after each action and after every
  solo run. If a save fails you see a red **SAVE FAILED** message and the game keeps retrying;
  it never says "saved" when it wasn't.
* **Backup:** `python -m server.backup` writes a timestamped copy to `saves/backups/` (safe while the
  server runs; keeps the newest 10). `python -m server.main --backup-on-start` backs up at startup.
* **Restore:** stop the server, copy a file from `saves/backups/` over `saves/game.db`, start again.
* Set a different database file with `--db PATH` or the `RPG_DB_PATH` environment variable.

## Controls
A/D move, W/Space jump, Shift dodge, **J / K** (rebindable) and **1-6** use the skill bound to that key,
Q/E/R potions (solo only), Esc pause/leave. Rebind keys at **Skills > Key Bindings**.

## Features
* **Characters:** up to 6 per account, each with its own class, level/XP, stats, skills, key bindings,
  inventory/equipment, gold, profession and dungeon progress. Create/select/delete (delete asks to confirm).
* **Stats:** Strength, Vitality, Defense, Agility, Intellect, Dexterity, Luck. Each has **+1 / +10 / +100 / +MAX**
  buttons (spends only what you have, max 5000 points per stat, never negative). The server validates and saves it.
* **Skills:** unlocked skills are separate from key bindings. Learn/upgrade with skill points; no cap on how many
  you keep (8 per class today, more can be added in `client/skills.py`). Skills have damage, cooldown, range,
  **energy cost** and unlock levels; types: melee, ranged, area/magic, buffs, defensive, healing, passives, god
  (ultimate) skills at levels 1000/2000/3000. J and K can hold any unlocked active skill or the basic attacks.
* **Leveling 1-3000** (`client/progression.py`): levels 1-25 keep the original fast curve; after that XP needs
  grow sharply (about 3x at 100, 23x at 500, 55x at 1000). XP from enemies far below your level shrinks to 5%.
  Level grades: F, E, D, C, B, A, S, God.
* **Marketplace** (Marketplace button): player listings (set your own price, 5% seller fee, max 10 listings,
  1 gold minimum), search, filters, sorting, cancel, history of your sales/purchases; goods are removed from your
  bag when listed. **NPC vendors:** Blacksmith, Armorer, Jeweler, Alchemist, General Store, Rare Dealer, with a
  confirmation screen; vendors buy items back at 30% of their price.
* **Arena:** PvP (1v1...5v5, FFA) with everyone scaled to level 30 so levels don't decide fights, plus **Co-op PvE**
  (2-4 players vs 7 shared enemies and a boss, shared XP/loot). Kill limits, time limit, respawns, "Play Again".
* **Solo:** endeavors in 100 dungeon levels, professions (level 10) and crafting, as before.

## Server options
`python -m server.main --host 0.0.0.0 --port 5555 --db saves/game.db --time-limit 180 --kill-limit 15 --respawn 3`
`--allow-small-matches` is a **testing option** (team modes start with 1 per team, co-op with 1 player).
By default a mode never starts until its exact player count is met.

## Security and trust model (read this)
* The server validates every request: types, ranges, sizes (64 KB), rate limits, login throttling, one session
  per account. Passwords are stored as salted scrypt hashes. All SQL is parameterized.
* **Server-authoritative:** PvP/co-op combat, damage, cooldowns, kills, match rewards, the marketplace, NPC
  vendors, stat allocation, skills, key bindings, equipping. Trades run in single database transactions.
* **Client-reported (trusted):** solo endeavor results (XP, gold, loot) and crafting are computed by the client and
  uploaded as a snapshot. The server rejects structurally invalid snapshots and anything touching stats, skills,
  bindings or equipment, but it **cannot verify solo XP/gold/loot**. Fine among friends; not cheat-proof.
* Traffic is **not encrypted** (plain TCP on your LAN): passwords and chat-free game data can be read by others
  on the same network. Use a throwaway password. Do not expose the port to the internet. Add TLS first.

## Tests
`python -m pip install -r requirements-dev.txt` then `python -m pytest -q` (about a minute: it starts real servers,
real TCP clients and separate processes). `DEV_MODE = True` in `client/settings.py` adds Home-screen shortcuts
(F1-F4 add levels, F5 gold/materials) so high levels can be tried without grinding.

## Not implemented yet
* Direct player-to-player **trade window** (the marketplace covers trading).
* **PostgreSQL** (SQLite only; all SQL is in `storage/database.py`).
* **Quests, achievements, appearance customization.**
* Explicit **parties/invites** and open-world co-op exploration (co-op is a queued, instanced fight).
* A per-lobby settings screen (limits are server options, not per-lobby menus).
* Encrypted transport; server-side verification of solo runs.
* Balance has been checked by simulation and tests, not by long human playtesting.

## Layout
`client/` game, UI and networking client  |  `server/` game server, arena simulation, backups
`shared/` protocol, economy rules, modes  |  `storage/` SQLite layer  |  `tests/`
(The server currently imports shared game rules from `client/` such as characters and combat; moving them
into `shared/` is a planned cleanup.)
