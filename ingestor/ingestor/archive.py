"""Keeps every raw source response so a bad parse can be replayed later."""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone


class LocalArchive:
    def __init__(self, directory: str):
        self.dir = pathlib.Path(directory)

    def save(self, run_id: str, symbol: str, raw: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.dir / day / run_id / f"{symbol}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw)
        return str(path)


class S3Archive:
    """IBM Cloud Object Storage speaks the S3 API, so boto3 works for it."""

    def __init__(self, bucket: str, endpoint: str, access_key: str, secret_key: str, client=None):
        self.bucket = bucket
        if client is None:
            import boto3
            client = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id=access_key,
                                  aws_secret_access_key=secret_key)
        self.client = client

    def save(self, run_id: str, symbol: str, raw: str) -> str:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"raw/{day}/{run_id}/{symbol}.json"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=raw.encode(), ContentType="application/json")
        return f"s3://{self.bucket}/{key}"


def make_archive():
    from stockplatform.config import env
    if env("ARCHIVE_BUCKET"):
        return S3Archive(env("ARCHIVE_BUCKET"), env("ARCHIVE_ENDPOINT"), env("ARCHIVE_ACCESS_KEY"),
                         env("ARCHIVE_SECRET_KEY"))
    return LocalArchive(env("ARCHIVE_DIR", "./archive"))
