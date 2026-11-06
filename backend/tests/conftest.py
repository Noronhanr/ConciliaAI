import os
from pathlib import Path

os.environ['DATABASE_URL'] = 'sqlite:////tmp/test_concilia.db'
os.environ['MINIO_ENDPOINT'] = 'localhost:9000'

import pytest
from fastapi.testclient import TestClient

from app.auth import password_hasher
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User


@pytest.fixture()
def client(monkeypatch):
    from app import main
    monkeypatch.setattr(main, 'ensure_bucket', lambda: None)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.add(User(username='teste', password_hash=password_hasher.hash('senha-forte'), role='operador'))
        db.commit()
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    Path('/tmp/test_concilia.db').unlink(missing_ok=True)