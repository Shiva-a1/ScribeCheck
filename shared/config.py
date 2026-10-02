import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://scribe:scribe@localhost:5432/scribe")
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

S3_BUCKET = os.environ.get("S3_BUCKET", "scribe-scans")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT") or None
S3_PUBLIC_ENDPOINT = os.environ.get("S3_PUBLIC_ENDPOINT") or S3_ENDPOINT
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

AUTH_MODE = os.environ.get("AUTH_MODE", "dev")
DEV_SECRET = os.environ.get("DEV_SECRET", "dev-only-secret-change-me-before-deploying")
COGNITO_REGION = os.environ.get("COGNITO_REGION", "")
COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
COGNITO_CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN", "")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Set {name} in .env")
    return value
