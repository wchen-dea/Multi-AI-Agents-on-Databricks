from .base import BaseSpecialistAgent

_SYSTEM = """You are a senior full-stack engineer who can seamlessly work across the entire stack.

Your responsibilities:
- Design and implement end-to-end features spanning frontend and backend
- Set up monorepo structures (Turborepo, Nx) and dev tooling
- Build Next.js / Nuxt applications with server-side rendering and API routes
- Design database schemas (PostgreSQL with Prisma or SQLAlchemy)
- Implement authentication flows (NextAuth, Clerk, Auth0, JWT)
- Wire up frontend data fetching (React Query, SWR, tRPC)
- Write Docker Compose setups for local development
- Configure CI/CD pipelines (GitHub Actions)
- Implement real-time features (WebSockets, SSE, Socket.io)
- Set up environment management, feature flags, logging

When writing code:
- Build cohesive features — consider both frontend UX and backend API design together
- Use TypeScript across the stack when possible
- Write proper error boundaries and loading states on the frontend
- Return consistent API response shapes with proper error codes on the backend
- Keep the dev experience smooth: hot reload, sensible defaults, clear README steps
- Co-locate related code (feature-based folder structure)

Always produce working, full-stack production-ready code."""


class FullStackAgent(BaseSpecialistAgent):
    name = "fullstack"
    role = "Full-Stack Engineer"
    system_prompt = _SYSTEM
    extra_tools = [
        {
            "name": "scaffold_feature",
            "description": "Scaffold a full-stack feature with API route + React page.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string", "description": "Feature name (e.g. 'dashboard', 'auth')."},
                    "base_path": {"type": "string", "description": "Base directory for the feature files."},
                },
                "required": ["feature", "base_path"],
            },
        }
    ]

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "scaffold_feature":
            feat = inputs["feature"]
            base = inputs["base_path"].rstrip("/")
            F = feat.capitalize()

            # API route (Next.js App Router)
            api_code = f'''import {{ NextRequest, NextResponse }} from "next/server";

export async function GET(req: NextRequest) {{
  return NextResponse.json({{ message: "GET /{feat} ok", data: [] }});
}}

export async function POST(req: NextRequest) {{
  const body = await req.json();
  // TODO: validate body with zod and persist to DB
  return NextResponse.json({{ message: "{F} created", data: body }}, {{ status: 201 }});
}}
'''
            # React page
            page_code = f'''"use client";

import {{ useEffect, useState }} from "react";

interface {F}Item {{
  id: string;
  // TODO: add fields
}}

export default function {F}Page() {{
  const [items, setItems] = useState<{F}Item[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {{
    fetch("/api/{feat}")
      .then((r) => r.json())
      .then((data) => setItems(data.data ?? []))
      .finally(() => setLoading(false));
  }}, []);

  if (loading) return <p className="p-8">Loading…</p>;

  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold mb-4">{F}</h1>
      {{items.length === 0 ? (
        <p className="text-gray-500">No items yet.</p>
      ) : (
        <ul className="space-y-2">
          {{items.map((item) => (
            <li key={{item.id}} className="border rounded p-3">
              {{JSON.stringify(item)}}
            </li>
          ))}}
        </ul>
      )}}
    </main>
  );
}}
'''
            self._write_file(f"{base}/app/api/{feat}/route.ts", api_code)
            self._write_file(f"{base}/app/{feat}/page.tsx", page_code)
            return f"Scaffolded {F} feature:\n  API → {base}/app/api/{feat}/route.ts\n  Page → {base}/app/{feat}/page.tsx"
        return super()._dispatch_tool(name, inputs)
