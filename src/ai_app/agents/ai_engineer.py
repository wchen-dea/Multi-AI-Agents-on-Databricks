from .base import BaseSpecialistAgent

_SYSTEM = """You are a senior AI engineer specializing in LLM applications, RAG systems, and AI product development.

Your responsibilities:
- Build LLM-powered applications using the Anthropic SDK (claude-opus-4-7 by default)
- Design RAG pipelines (chunking, embedding, vector search, retrieval, reranking)
- Implement agentic systems with tool use and multi-step reasoning
- Prompt engineering: few-shot examples, chain-of-thought, structured outputs
- Integrate vector databases (Pinecone, Weaviate, pgvector, ChromaDB)
- Build evaluation frameworks for LLM outputs
- Fine-tuning workflows and RLHF/RLAIF data pipelines
- Implement streaming responses and token usage tracking
- Guardrails, safety filters, content moderation

When writing code:
- Always use claude-opus-4-7 with adaptive thinking for complex reasoning tasks
- Use streaming for long completions
- Track token usage and costs
- Implement retry logic with exponential backoff
- Cache expensive embeddings/completions where appropriate
- Use structured outputs (Pydantic) to parse LLM responses reliably
- Write evaluation harnesses to measure output quality

Always produce working, production-ready AI engineering code using the official Anthropic Python SDK."""


class AIEngineerAgent(BaseSpecialistAgent):
    name = "ai_engineer"
    role = "AI Engineer"
    system_prompt = _SYSTEM
    extra_tools = [
        {
            "name": "scaffold_rag_pipeline",
            "description": "Scaffold a RAG pipeline with embedding + retrieval boilerplate.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "vector_store": {
                        "type": "string",
                        "enum": [
                            "chromadb",
                            "databricks_uc",
                            "databricks_feature_store",
                            "databricks_lakebase_mcp",
                            "pgvector",
                            "pinecone",
                            "in_memory",
                        ],
                        "description": "Vector store backend.",
                    },
                    "path": {"type": "string", "description": "Output file path."},
                },
                "required": ["vector_store", "path"],
            },
        },
        {
            "name": "scaffold_agent",
            "description": "Scaffold a Claude agentic loop with tool use.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string", "description": "Agent class name."},
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tool names to include.",
                    },
                    "path": {"type": "string", "description": "Output file path."},
                },
                "required": ["agent_name", "path"],
            },
        },
    ]

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "scaffold_rag_pipeline":
            vs = inputs["vector_store"]
            path = inputs["path"]

            if vs == "chromadb":
                vector_store_setup = (
                    "import chromadb\n"
                    "_chroma = chromadb.Client()\n"
                    "_collection = _chroma.get_or_create_collection('rag')"
                )
                index_impl = "    _collection.add(documents=docs, embeddings=embeddings, ids=ids)"
                retrieve_impl = (
                    "    results = _collection.query(query_embeddings=[q_emb], n_results=top_k)\n"
                    "    return results[\"documents\"][0]"
                )
            elif vs == "databricks_uc":
                vector_store_setup = (
                    "from ai_app.integrations.mcp_data_sources import DataSourceType, MCPDataSourceGateway\n"
                    "\n"
                    "gateway = MCPDataSourceGateway.from_env(DataSourceType.DATABRICKS_UC)"
                )
                index_impl = (
                    "    # Managed Unity Catalog data is generally maintained by upstream pipelines.\n"
                    "    # Keep indexing as a no-op in this scaffold.\n"
                    "    _ = (docs, ids, embeddings)"
                )
                retrieve_impl = "    return gateway.retrieve(query=query, top_k=top_k)"
            elif vs == "databricks_feature_store":
                vector_store_setup = (
                    "from ai_app.integrations.mcp_data_sources import DataSourceType, MCPDataSourceGateway\n"
                    "\n"
                    "gateway = MCPDataSourceGateway.from_env(DataSourceType.DATABRICKS_FEATURE_STORE)"
                )
                index_impl = (
                    "    # Feature tables are usually maintained by offline feature pipelines.\n"
                    "    # Keep indexing as a no-op in this scaffold; use feature jobs for writes.\n"
                    "    _ = (docs, ids, embeddings)"
                )
                retrieve_impl = "    return gateway.retrieve(query=query, top_k=top_k)"
            elif vs == "databricks_lakebase_mcp":
                vector_store_setup = (
                    "from ai_app.integrations.mcp_data_sources import DataSourceType, MCPDataSourceGateway\n"
                    "\n"
                    "gateway = MCPDataSourceGateway.from_env(DataSourceType.DATABRICKS_LAKEBASE_MCP)"
                )
                index_impl = (
                    "    # Databricks Lakebase is typically pre-ingested and served through MCP tools.\n"
                    "    # Keep indexing as a no-op unless your MCP server exposes an upsert tool.\n"
                    "    _ = (docs, ids, embeddings)"
                )
                retrieve_impl = "    return gateway.retrieve(query=query, top_k=top_k)"
            else:
                vector_store_setup = "# Configure your vector store here"
                index_impl = "    # Store (embeddings, docs) in your vector store"
                retrieve_impl = (
                    "    # Query your vector store and return document strings\n"
                    f"    raise NotImplementedError(\"Implement retrieval for {vs}\")"
                )

            code = f'''"""RAG pipeline using {vs} for vector storage."""

from __future__ import annotations
import os
from typing import Any
import anthropic

# ── Embedding (replace with your preferred provider) ─────────────────────────

def embed(text: str) -> list[float]:
    """Return a dense embedding vector for *text*."""
    # Example: use OpenAI, Cohere, or a local model
    # from openai import OpenAI
    # return OpenAI().embeddings.create(input=text, model="text-embedding-3-small").data[0].embedding
    raise NotImplementedError("Plug in your embedding provider here.")


# ── Vector store: {vs} ───────────────────────────────────────────────────────

{vector_store_setup}


def index_documents(docs: list[str], ids: list[str]) -> None:
    """Embed and store documents."""
    embeddings = [embed(d) for d in docs]
{index_impl}


def retrieve(query: str, top_k: int = 5) -> list[str]:
    """Retrieve top-k relevant documents for *query*."""
    q_emb = embed(query)
{retrieve_impl}


# ── RAG chain ─────────────────────────────────────────────────────────────────

def rag_answer(question: str, top_k: int = 5) -> str:
    """Retrieve relevant context and answer the question with Claude."""
    context_docs = retrieve(question, top_k=top_k)
    context = "\\n\\n".join(f"[{{i+1}}] {{doc}}" for i, doc in enumerate(context_docs))

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        thinking={{"type": "adaptive"}},
        system=(
            "You are a helpful assistant. Answer the user\\'s question using ONLY "
            "the provided context. If the answer isn\\'t in the context, say so."
        ),
        messages=[
            {{
                "role": "user",
                "content": f"Context:\\n{{context}}\\n\\nQuestion: {{question}}",
            }}
        ],
    )
    for block in response.content:
        if hasattr(block, "text"):
            return block.text
    return ""


if __name__ == "__main__":
    # Quick smoke test
    index_documents(
        docs=["The capital of France is Paris.", "Python was created by Guido van Rossum."],
        ids=["doc1", "doc2"],
    )
    print(rag_answer("What is the capital of France?"))
'''
            self._write_file(path, code)
            return f"Scaffolded RAG pipeline ({vs}) → {path}"

        if name == "scaffold_agent":
            agent_name = inputs["agent_name"]
            tools_list = inputs.get("tools", ["search", "calculator"])
            path = inputs["path"]
            tools_schema = "\n".join(
                f'''    {{
        "name": "{t}",
        "description": "TODO: describe the {t} tool.",
        "input_schema": {{
            "type": "object",
            "properties": {{
                "input": {{"type": "string"}},
            }},
            "required": ["input"],
        }},
    }},'''
                for t in tools_list
            )
            code = f'''"""Claude agentic loop — {agent_name}."""

from __future__ import annotations
import os
import anthropic

TOOLS = [
{tools_schema}
]

MODEL = "claude-opus-4-7"
MAX_ITER = 20


def dispatch_tool(name: str, inputs: dict) -> str:
    """Execute a tool call and return string output."""
    # TODO: implement tool logic
    return f"Tool {{name}} called with {{inputs}}"


class {agent_name}:
    def __init__(self, api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

    def run(self, task: str) -> str:
        messages = [{{"role": "user", "content": task}}]

        for _ in range(MAX_ITER):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=4096,
                thinking={{"type": "adaptive"}},
                tools=TOOLS,
                messages=messages,
            )
            messages.append({{"role": "assistant", "content": response.content}})

            if response.stop_reason == "end_turn":
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = dispatch_tool(block.name, block.input)
                    tool_results.append({{
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    }})
            messages.append({{"role": "user", "content": tool_results}})

        return "Max iterations reached."


if __name__ == "__main__":
    agent = {agent_name}()
    print(agent.run("Hello! What can you do?"))
'''
            self._write_file(path, code)
            return f"Scaffolded {agent_name} agent → {path}"

        return super()._dispatch_tool(name, inputs)
