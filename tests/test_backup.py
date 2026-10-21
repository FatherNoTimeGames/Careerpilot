import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from careerpilot.backup import create_backup, verify_backup
from careerpilot.store import connect


class BackupTests(unittest.TestCase):
    def test_live_wal_roundtrip_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite3'
            destination = Path(directory) / 'snapshot.sqlite3'
            db = connect(source)
            original = b'private original document\x00\xff'
            db.execute("INSERT INTO resume_documents(filename,kind,sha256,original,extracted_text,warnings,created_at) VALUES (?,?,?,?,?,?,?)",
                       ('resume.pdf', 'pdf', 'hash', original, 'text', '[]', 'today'))
            db.execute("INSERT INTO career_profiles(facts,verified,created_at) VALUES ('[]',1,'today')")
            db.commit()
            self.assertTrue(Path(str(source) + '-wal').exists())
            counts = create_backup(source, destination)
            self.assertEqual(counts['resume_documents'], 1)
            self.assertEqual(counts['career_profiles'], 1)
            self.assertEqual(os.stat(destination).st_mode & 0o777, 0o600)
            restored = sqlite3.connect(destination)
            self.assertEqual(restored.execute('SELECT original FROM resume_documents').fetchone()[0], original)
            restored.close()
            self.assertFalse(Path(str(destination) + '-wal').exists())
            with self.assertRaises(FileExistsError):
                create_backup(source, destination)
            db.close()

    def test_missing_invalid_and_broken_references_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing'
            with self.assertRaises(FileNotFoundError):
                verify_backup(missing)
            self.assertFalse(missing.exists())
            missing.write_bytes(b'not sqlite')
            with self.assertRaises(sqlite3.DatabaseError):
                verify_backup(missing)
            wrong = Path(directory) / 'wrong'
            sqlite3.connect(wrong).close()
            with self.assertRaises(ValueError):
                verify_backup(wrong)
            source = Path(directory) / 'source'
            db = connect(source)
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute("INSERT INTO job_resumes VALUES (999,999,'today')")
            db.commit()
            with self.assertRaises(ValueError):
                create_backup(source, Path(directory) / 'failed')
            self.assertFalse((Path(directory) / 'failed').exists())
            self.assertFalse(list(Path(directory).glob('.careerpilot-backup-*')))
            db.close()
