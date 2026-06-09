from .base import BaseSpecialistAgent

_SYSTEM = """You are a senior backend engineer specializing in Python (FastAPI/Django), Node.js, databases, and distributed systems.

Your responsibilities:
- Design and implement REST and GraphQL APIs
- Write clean, typed Python (FastAPI, Pydantic v2, SQLAlchemy 2.x)
- Implement authentication (JWT, OAuth2, sessions)
- Design relational and NoSQL schemas (PostgreSQL, MongoDB, Redis)
- Write database migrations (Alembic, Prisma)
- Implement caching, rate limiting, background tasks (Celery, arq)
- Write integration and unit tests (pytest, httpx)
- Handle security: input validation, SQL injection, XSS prevention

When writing code:
- Follow 12-factor app principles
- Use dependency injection patterns
- Write idiomatic, type-annotated Python
- Include error handling and proper HTTP status codes
- Document API endpoints with OpenAPI schemas
- Write pytest tests for all endpoints

Always produce working, production-ready code."""


class BackendAgent(BaseSpecialistAgent):
    name = "backend"
    role = "Backend Engineer"
    system_prompt = _SYSTEM
    extra_tools = [
        {
            "name": "scaffold_endpoint",
            "description": "Scaffold a FastAPI router with CRUD endpoints.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "resource": {"type": "string", "description": "Resource name (e.g. 'user', 'product')."},
                    "path": {"type": "string", "description": "Output file path."},
                },
                "required": ["resource", "path"],
            },
        }
    ]

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "scaffold_endpoint":
            resource = inputs["resource"]
            path = inputs["path"]
            r = resource.capitalize()
            code = f'''from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/{resource}s", tags=["{r}"])


class {r}Base(BaseModel):
    name: str
    description: Optional[str] = None


class {r}Create({r}Base):
    pass


class {r}Response({r}Base):
    id: int

    model_config = {{"from_attributes": True}}


# In-memory store — replace with DB session
_store: dict[int, dict] = {{}}
_counter = 0


@router.get("/", response_model=list[{r}Response])
async def list_{resource}s():
    return list(_store.values())


@router.post("/", response_model={r}Response, status_code=status.HTTP_201_CREATED)
async def create_{resource}(body: {r}Create):
    global _counter
    _counter += 1
    item = {{"id": _counter, **body.model_dump()}}
    _store[_counter] = item
    return item


@router.get("/{{id}}", response_model={r}Response)
async def get_{resource}(id: int):
    item = _store.get(id)
    if not item:
        raise HTTPException(status_code=404, detail="{r} not found")
    return item


@router.delete("/{{id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_{resource}(id: int):
    if id not in _store:
        raise HTTPException(status_code=404, detail="{r} not found")
    del _store[id]
'''
            self._write_file(path, code)
            return f"Scaffolded {r} CRUD router → {path}"
        return super()._dispatch_tool(name, inputs)
