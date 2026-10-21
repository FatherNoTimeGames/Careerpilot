"""Local owner-password bootstrap; never prints or commits credential values."""
import os
import secrets
from pathlib import Path


def password_path(db_path):
    return Path(db_path).resolve().parent / 'owner-password'


def initialize_password(db_path):
    path = password_path(db_path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path
    with os.fdopen(fd, 'w') as file:
        file.write(secrets.token_urlsafe(32) + '\n')
    return path


def owner_password(db_path):
    if os.environ.get('CAREERPILOT_PASSWORD'):
        return os.environ['CAREERPILOT_PASSWORD']
    path = password_path(db_path)
    return path.read_text().strip() if path.exists() else ''
