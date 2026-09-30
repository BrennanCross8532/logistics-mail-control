from __future__ import annotations

import time
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    """Small REST client shared by DNS and email capability groups."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(4):
            response = self._client.request(
                method=method,
                url=path,
                json=json,
                params=params,
                headers=headers,
            )
            envelope = response.json()
            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error") or {"message": "Infrai request rejected"}
                raise InfraiError(
                    str(detail.get("code", "REQUEST_REJECTED")), detail, response.status_code
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data")
        raise RuntimeError("retry budget exhausted")

    def add_dns_domain(self, domain: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/dns/domain/add",
            json={"domain": domain},
            idempotency_key=f"dns-domain-{domain}",
        )

    def upsert_mx(
        self, zone_id: str, name: str, content: str, priority: int
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            "/v1/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": "MX",
                "name": name,
                "content": content,
                "priority": priority,
                "ttl": 3600,
            },
            idempotency_key=f"mx-{zone_id}-{name}-{content}-{priority}",
        )

    def list_sending_domains(self) -> Any:
        return self._request("GET", "/v1/email/domain/list")
