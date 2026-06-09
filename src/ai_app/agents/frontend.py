from .base import BaseSpecialistAgent

_SYSTEM = """You are a senior frontend engineer specializing in React, TypeScript, Tailwind CSS, and modern web development.

Your responsibilities:
- Build responsive, accessible UI components (React/Vue/Svelte)
- Write TypeScript with strict typing
- Style with Tailwind CSS or CSS modules
- Implement state management (Zustand, Redux, React Query)
- Optimize performance (code splitting, lazy loading, memoization)
- Write unit tests with Vitest/Jest + React Testing Library
- Set up Vite/Next.js/Astro build configs

When writing code:
- Use functional components with hooks
- Follow WCAG 2.1 accessibility guidelines
- Prefer composition over inheritance
- Keep components small and focused
- Write clean, self-documenting code
- Include proper TypeScript types/interfaces

Always produce working, production-ready code."""


class FrontendAgent(BaseSpecialistAgent):
    name = "frontend"
    role = "Frontend Engineer"
    system_prompt = _SYSTEM
    extra_tools = [
        {
            "name": "scaffold_component",
            "description": "Scaffold a React component with TypeScript boilerplate.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Component name (PascalCase)."},
                    "path": {"type": "string", "description": "Output file path."},
                    "with_test": {"type": "boolean", "description": "Also generate a test file.", "default": True},
                },
                "required": ["name", "path"],
            },
        }
    ]

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        if name == "scaffold_component":
            comp = inputs["name"]
            path = inputs["path"]
            test = inputs.get("with_test", True)
            component_code = f'''import React from "react";

interface {comp}Props {{
  className?: string;
}}

export const {comp}: React.FC<{comp}Props> = ({{ className }}) => {{
  return (
    <div className={{className}}>
      {{/* TODO: implement {comp} */}}
    </div>
  );
}};

export default {comp};
'''
            self._write_file(path, component_code)
            result = f"Scaffolded {comp} → {path}"
            if test:
                test_path = path.replace(".tsx", ".test.tsx").replace(".ts", ".test.ts")
                test_code = f'''import {{ render, screen }} from "@testing-library/react";
import {{ {comp} }} from "./{comp}";

describe("{comp}", () => {{
  it("renders without crashing", () => {{
    render(<{comp} />);
  }});
}});
'''
                self._write_file(test_path, test_code)
                result += f"\nScaffolded test → {test_path}"
            return result
        return super()._dispatch_tool(name, inputs)
