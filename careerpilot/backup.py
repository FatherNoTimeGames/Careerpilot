"""Consistent local SQLite snapshots. Backups contain private candidate data."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile


REQUIRED_TABLES = {'jobs', 'settings', 'career_profiles', 'resume_documents', 'resume_versions'}


def _readonly(path):
    path = Path(path).resolve(strict=True)
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)


def verify_backup(path):
    """Read without migrations, creation, or changes to the inspected database."""
    with closing(_readonly(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES <= tables:
            raise ValueError('Not a supported CareerPilot database')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Database contains broken references')
        return {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in sorted(REQUIRED_TABLES)}


def create_backup(source, destination):
    """Online backup includes committed WAL data; never replaces an existing file."""
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('Backup destination already exists')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.careerpilot-backup-', dir=destination.parent)
    os.close(fd)
    try:
        source_db = _readonly(source)
        target_db = sqlite3.connect(temporary)
        try:
            source_db.backup(target_db, pages=256, sleep=0.05)
            # A standalone snapshot must not depend on WAL sidecars.
            target_db.execute('PRAGMA journal_mode=DELETE')
        finally:
            target_db.close()
            source_db.close()
        counts = verify_backup(temporary)
        with open(temporary, 'rb') as snapshot:
            os.fsync(snapshot.fileno())
        # Hard-link publication is atomic and fails if another writer won the name.
        os.link(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return counts
    finally:
        Path(temporary).unlink(missing_ok=True)
