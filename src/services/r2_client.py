"""Cloudflare R2 storage client.

This module provides a client for interacting with Cloudflare R2 storage,
implementing the data lake operations specified in the OmniFeed architecture.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from src.utils.config import R2Config

logger = logging.getLogger(__name__)


class R2Client:
    """Client for Cloudflare R2 storage."""

    def __init__(self, config: Optional[R2Config] = None) -> None:
        self._config = config or R2Config()
        self._client = boto3.client(
            "s3",
            endpoint_url=self._config.endpoint_url,
            aws_access_key_id=self._config.access_key_id,
            aws_secret_access_key=self._config.secret_access_key,
            region_name="auto",
        )

    def get_object(self, key: str) -> Optional[dict[str, Any]]:
        """Get an object from R2 storage.

        Args:
            key: The object key (path).

        Returns:
            The parsed JSON object, or None if not found.
        """
        try:
            response = self._client.get_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            body = response["Body"].read().decode("utf-8")
            return json.loads(body)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                logger.info(f"Object not found: {key}")
                return None
            logger.error(f"Failed to get object {key}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to get object {key}: {e}")
            raise

    def put_object(
        self,
        key: str,
        data: dict[str, Any] | list[Any],
        content_type: str = "application/json",
    ) -> str:
        """Put an object to R2 storage.

        Args:
            key: The object key (path).
            data: The data to store (will be JSON serialized).
            content_type: The content type.

        Returns:
            The ETag of the uploaded object.
        """
        try:
            body = json.dumps(data, ensure_ascii=False, default=str, indent=2)
            response = self._client.put_object(
                Bucket=self._config.bucket_name,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType=content_type,
            )
            etag = response.get("ETag", "")
            logger.info(f"Uploaded object {key} with ETag {etag}")
            return etag
        except Exception as e:
            logger.error(f"Failed to put object {key}: {e}")
            raise

    def put_xml_object(self, key: str, xml_content: str) -> str:
        """Put an XML object to R2 storage.

        Args:
            key: The object key (path).
            xml_content: The XML content as string.

        Returns:
            The ETag of the uploaded object.
        """
        try:
            response = self._client.put_object(
                Bucket=self._config.bucket_name,
                Key=key,
                Body=xml_content.encode("utf-8"),
                ContentType="application/rss+xml; charset=utf-8",
            )
            etag = response.get("ETag", "")
            logger.info(f"Uploaded XML object {key} with ETag {etag}")
            return etag
        except Exception as e:
            logger.error(f"Failed to put XML object {key}: {e}")
            raise

    def get_object_etag(self, key: str) -> Optional[str]:
        """Get the ETag of an object without downloading it.

        Args:
            key: The object key (path).

        Returns:
            The ETag string, or None if not found.
        """
        try:
            response = self._client.head_object(
                Bucket=self._config.bucket_name,
                Key=key,
            )
            return response.get("ETag")
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            logger.error(f"Failed to get ETag for {key}: {e}")
            raise

    def put_object_with_etag(
        self,
        key: str,
        data: dict[str, Any],
        expected_etag: str,
    ) -> bool:
        """Put an object with ETag conditional write (optimistic locking).

        Args:
            key: The object key (path).
            data: The data to store.
            expected_etag: The expected ETag for conditional write.

        Returns:
            True if successful, False if ETag mismatch (412 Precondition Failed).
        """
        try:
            body = json.dumps(data, ensure_ascii=False, default=str, indent=2)
            self._client.put_object(
                Bucket=self._config.bucket_name,
                Key=key,
                Body=body.encode("utf-8"),
                ContentType="application/json",
                **{"IfMatch": expected_etag},
            )
            return True
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "PreconditionFailed":
                logger.warning(f"ETag mismatch for {key}, expected {expected_etag}")
                return False
            raise

    def load_sliding_window(self, key: str = "snapshot/sliding_window.json") -> dict[str, Any]:
        """Load the sliding window snapshot from R2.

        Returns:
            Dictionary of event IDs to timestamps.
        """
        data = self.get_object(key)
        if data is None:
            return {}
        return data.get("events", {})

    def save_sliding_window(
        self,
        window: dict[str, datetime],
        key: str = "snapshot/sliding_window.json",
    ) -> str:
        """Save the sliding window snapshot to R2.

        Args:
            window: Dictionary of event IDs to timestamps.

        Returns:
            The ETag of the uploaded object.
        """
        data = {
            "events": {
                eid: ts.isoformat() for eid, ts in window.items()
            }
        }
        return self.put_object(key, data)

    def load_whitelist(self, key: str = "config/whitelist.json") -> list[str]:
        """Load the ticker whitelist from R2.

        Returns:
            List of ticker symbols.
        """
        data = self.get_object(key)
        if data is None:
            return []
        return data.get("tickers", [])

    def save_whitelist(
        self,
        tickers: list[str],
        key: str = "config/whitelist.json",
    ) -> str:
        """Save the ticker whitelist to R2.

        Args:
            tickers: List of ticker symbols.

        Returns:
            The ETag of the uploaded object.
        """
        data = {
            "tickers": tickers,
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
        }
        return self.put_object(key, data)
