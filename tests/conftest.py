"""
Test environment bootstrap.

Sets the env vars the vinayak package requires BEFORE any vinayak import
happens, so the suite runs identically on a dev machine (where .env exists)
and in CI (where it doesn't). setdefault never overrides real values.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("VINAYAK_DEV_MODE", "1")
os.environ.setdefault("JWT_SECRET", "unit-test-secret-not-for-production")
os.environ.setdefault("INTERNAL_API_KEY", "unit-test-internal-key")
