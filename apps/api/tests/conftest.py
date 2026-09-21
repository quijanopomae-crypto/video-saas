import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("AUTH_JWT_SECRET", "test-only-secret-not-valid-for-production-0123456789")
