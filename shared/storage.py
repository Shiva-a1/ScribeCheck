from functools import cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from shared import config


@cache
def _client(endpoint):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=config.AWS_REGION,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket():
    if not config.S3_ENDPOINT:
        return
    client = _client(config.S3_ENDPOINT)
    try:
        client.head_bucket(Bucket=config.S3_BUCKET)
    except ClientError:
        client.create_bucket(Bucket=config.S3_BUCKET)


def put(key, data, content_type):
    _client(config.S3_ENDPOINT).put_object(
        Bucket=config.S3_BUCKET, Key=key, Body=data, ContentType=content_type
    )


def get(key):
    response = _client(config.S3_ENDPOINT).get_object(Bucket=config.S3_BUCKET, Key=key)
    return response["Body"].read()


def url(key, expires=600):
    return _client(config.S3_PUBLIC_ENDPOINT).generate_presigned_url(
        "get_object", Params={"Bucket": config.S3_BUCKET, "Key": key}, ExpiresIn=expires
    )
