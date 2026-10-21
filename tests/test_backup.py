import os
import time

from client.character import Character
from server.backup import backup_database
from storage.database import Database


def test_backup_is_a_consistent_restorable_copy_and_prunes_old_ones(tmp_path):
    src = str(tmp_path / "game.db")
    db = Database(src)
    a = db.create_account("alice", "secret1")
    cid = db.create_character(a, "Hero", Character(name="Hero").to_dict())
    db.update_character(a, cid, lambda d: d.update(gold=321))
    out = str(tmp_path / "backups")
    first = backup_database(src, out, keep=2)                        # taken while the database is open/in use
    db.update_character(a, cid, lambda d: d.update(gold=999))          # later change is NOT in the backup
    restored = Database(first)
    assert restored.authenticate("alice", "secret1") == a
    assert restored.load_character(a, cid)[0]["gold"] == 321
    restored.close()
    for _ in range(3):
        backup_database(src, out, keep=2)
    assert len(os.listdir(out)) == 2
    db.close()
