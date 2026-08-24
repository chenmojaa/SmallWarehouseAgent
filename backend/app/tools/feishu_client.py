"""Feishu (Lark) Open API client.

Covers:
  - tenant_access_token acquisition + caching (TTL ~2h, refreshed proactively)
  - list wiki spaces
  - list nodes (recursive: walk children via parent_node_token)
  - get a docx node's raw text content
  - list bitable fields and records (records are returned as Markdown table rows)

Auth: internal app (App ID + App Secret -> tenant_access_token).
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from app.config import settings


class FeishuError(RuntimeError):
    """Raised when the Feishu API returns a non-zero code or HTTP error."""

    def __init__(self, code: int | str, msg: str, endpoint: str = ""):
        self.code = code
        self.msg = msg
        self.endpoint = endpoint
        super().__init__(f"[{endpoint}] Feishu error {code}: {msg}")


class FeishuClient:
    """Thread-safe lazy-token client."""

    def __init__(self, app_id: str | None = None, app_secret: str | None = None,
                 api_base: str | None = None, timeout: float = 30.0):
        self.app_id = app_id or settings.feishu_app_id
        self.app_secret = app_secret or settings.feishu_app_secret
        self.api_base = (api_base or settings.feishu_api_base).rstrip("/")
        self.timeout = timeout
        self._token: str | None = None
        self._token_expire_at: float = 0.0
        self._lock = threading.Lock()
        self._http = httpx.Client(timeout=timeout)

    # ----- token -----
    def _ensure_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._token_expire_at - 60:
                return self._token
            r = self._http.post(
                f"{self.api_base}/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            r.raise_for_status()
            j = r.json()
            if j.get("code") != 0:
                raise FeishuError(j.get("code"), j.get("msg"), "auth.tenant_access_token")
            self._token = j["tenant_access_token"]
            self._token_expire_at = time.time() + int(j.get("expire", 7200))
            return self._token

    # ----- low-level request -----
    def _request(self, method: str, path: str, params: dict | None = None,
                 json_body: dict | None = None) -> dict:
        token = self._ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = self.api_base + path
        r = self._http.request(method, url, params=params, json=json_body, headers=headers, timeout=self.timeout)
        if r.status_code >= 400:
            raise FeishuError(r.status_code, r.text[:500], path)
        j = r.json()
        if j.get("code") != 0:
            raise FeishuError(j.get("code"), j.get("msg"), path)
        return j.get("data", {})

    def close(self) -> None:
        self._http.close()

    # ----- wiki spaces -----
    def list_spaces(self, page_size: int | None = None) -> list[dict]:
        ps = page_size or settings.feishu_page_size
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict = {"page_size": ps}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", "/open-apis/wiki/v2/spaces", params=params)
            items.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items

    # ----- wiki nodes -----
    def list_nodes(self, space_id: str, parent_node_token: str | None = None,
                   page_size: int | None = None) -> list[dict]:
        ps = page_size or settings.feishu_page_size
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict = {"page_size": ps}
            if parent_node_token:
                params["parent_node_token"] = parent_node_token
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", f"/open-apis/wiki/v2/spaces/{space_id}/nodes", params=params)
            items.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items

    def walk_nodes(self, space_id: str, page_size: int | None = None):
        """Yield every node in the space (DFS)."""
        stack: list[str | None] = [None]  # root has no parent
        while stack:
            parent = stack.pop()
            for node in self.list_nodes(space_id, parent_node_token=parent, page_size=page_size):
                yield node
                if node.get("has_child"):
                    stack.append(node.get("node_token"))

    def get_node(self, space_id: str, node_token: str) -> dict:
        data = self._request("GET", f"/open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}")
        return data.get("node", {})

    # ----- docx -----
    def get_docx_raw_content(self, doc_id: str) -> str:
        data = self._request("GET", f"/open-apis/docx/v1/documents/{doc_id}/raw_content")
        return data.get("content", "")

    # ----- bitable -----
    def list_bitable_tables(self, app_token: str) -> list[dict]:
        data = self._request("GET", f"/open-apis/bitable/v1/apps/{app_token}/tables")
        return data.get("items", [])

    def list_bitable_fields(self, app_token: str, table_id: str) -> list[dict]:
        data = self._request("GET", f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields")
        return data.get("items", [])

    def list_bitable_records(self, app_token: str, table_id: str,
                             page_size: int | None = None) -> list[dict]:
        ps = page_size or settings.feishu_page_size
        items: list[dict] = []
        page_token: str | None = None
        while True:
            params: dict = {"page_size": ps}
            if page_token:
                params["page_token"] = page_token
            data = self._request(
                "GET",
                f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )
            items.extend(data.get("items", []))
            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
        return items
