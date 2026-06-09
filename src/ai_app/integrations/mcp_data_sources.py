"""MCP-based integration layer for multiple Databricks-backed data sources."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib import request


class DataSourceType(str, Enum):
    DATABRICKS_UC = "databricks_uc"
    DATABRICKS_FEATURE_STORE = "databricks_feature_store"
    DATABRICKS_LAKEBASE_MCP = "databricks_lakebase_mcp"


@dataclass
class MCPDataSourceGateway:
    """Unified MCP gateway for fetching knowledge context from multiple sources."""

    source_type: DataSourceType
    mcp_url: str
    token: str = ""
    timeout_seconds: int = 30
    tool_map: dict[DataSourceType, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls, source_type: DataSourceType) -> "MCPDataSourceGateway":
        return cls(
            source_type=source_type,
            mcp_url=os.environ["DATABRICKS_MCP_URL"],
            token=os.environ.get("DATABRICKS_TOKEN", ""),
            tool_map={
                DataSourceType.DATABRICKS_UC: os.environ.get(
                    "DATABRICKS_MCP_UC_TOOL", "unity_catalog_search"
                ),
                DataSourceType.DATABRICKS_FEATURE_STORE: os.environ.get(
                    "DATABRICKS_MCP_FEATURE_STORE_TOOL", "feature_store_search"
                ),
                DataSourceType.DATABRICKS_LAKEBASE_MCP: os.environ.get(
                    "DATABRICKS_MCP_LAKEBASE_TOOL", "lakebase_search"
                ),
            },
        )

    def retrieve(self, query: str, top_k: int = 5) -> list[str]:
        payload = self._payload_for_source(query=query, top_k=top_k)
        response = self._call_tool(tool_name=self.tool_map[self.source_type], payload=payload)
        return self._extract_documents(response)

    def _payload_for_source(self, query: str, top_k: int) -> dict[str, Any]:
        catalog = os.environ.get("UC_CATALOG", "main")
        schema = os.environ.get("UC_SCHEMA", "default")

        if self.source_type == DataSourceType.DATABRICKS_UC:
            return {
                "catalog": catalog,
                "schema": schema,
                "table": os.environ.get("UC_KB_TABLE", "knowledge_base_chunks"),
                "query": query,
                "top_k": top_k,
            }

        if self.source_type == DataSourceType.DATABRICKS_FEATURE_STORE:
            return {
                "catalog": catalog,
                "schema": schema,
                "table": os.environ.get("UC_FEATURE_TABLE", "kb_features"),
                "text_column": os.environ.get("UC_FEATURE_TEXT_COLUMN", "document_text"),
                "score_column": os.environ.get("UC_FEATURE_SCORE_COLUMN", "relevance_score"),
                "query": query,
                "top_k": top_k,
            }

        return {
            "catalog": catalog,
            "schema": schema,
            "table": os.environ.get("LAKEBASE_TABLE", "knowledge_base_chunks"),
            "query": query,
            "top_k": top_k,
        }

    def _call_tool(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        body = json.dumps({"tool": tool_name, "arguments": payload}).encode("utf-8")
        req = request.Request(self.mcp_url, data=body, headers=headers, method="POST")

        with request.urlopen(req, timeout=self.timeout_seconds) as res:
            return json.loads(res.read().decode("utf-8"))

    def _extract_documents(self, response: dict[str, Any]) -> list[str]:
        docs = response.get("documents")
        if isinstance(docs, list):
            return [str(d) for d in docs]

        result = response.get("result")
        if isinstance(result, dict):
            nested_docs = result.get("documents")
            if isinstance(nested_docs, list):
                return [str(d) for d in nested_docs]

        rows = response.get("rows")
        if not isinstance(rows, list):
            raise ValueError(f"Unexpected MCP response shape: {response}")

        extracted: list[str] = []
        for row in rows:
            if isinstance(row, dict):
                for key in ("document", "chunk_text", "text", "content"):
                    if key in row and row[key] is not None:
                        extracted.append(str(row[key]))
                        break
            elif row is not None:
                extracted.append(str(row))

        return extracted