"""
LangGraphSupervisorAgent — alternate orchestration implementation using LangGraph.

This implementation keeps the same specialist agents, shared memory, and message bus,
but executes orchestration through a LangGraph state machine:
  1. plan        -> create specialist work plan from task + memory snapshot
  2. execute     -> run specialists in parallel batches by plan group
  3. synthesize  -> produce final report from specialist outputs + collaboration state
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

import anthropic
from langgraph.graph import END, START, StateGraph

from .agents import AgentResult, SPECIALIST_NAMES, SPECIALIST_REGISTRY
from .settings import MODEL, MAX_TOKENS
from .supervisor import SupervisorResult
from .utils import MessageBus, SharedMemory

LOGGER = logging.getLogger(__name__)


@dataclass
class PlannedCall:
    specialist: str
    task: str
    context: str = ""
    group: int = 0


class GraphState(TypedDict, total=False):
    task: str
    plan: list[dict[str, Any]]
    specialist_results: list[dict[str, Any]]
    final_output: str


class LangGraphSupervisorAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        project_root: str = ".",
        verbose: bool = True,
        max_workers: int = 4,
        memory: SharedMemory | None = None,
        bus: MessageBus | None = None,
    ):
        self.client = client
        self.project_root = str(Path(project_root).resolve())
        self.verbose = verbose
        self.max_workers = max_workers

        self.memory = memory or SharedMemory()
        self.bus = bus or MessageBus()
        self._specialist_results: list[AgentResult] = []
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("plan", self._plan_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("synthesize", self._synthesize_node)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "synthesize")
        graph.add_edge("synthesize", END)
        return graph.compile()

    def _make_specialist(self, name: str) -> Any:
        cls = SPECIALIST_REGISTRY[name]
        return cls(
            client=self.client,
            project_root=self.project_root,
            verbose=self.verbose,
            memory=self.memory,
            bus=self.bus,
        )

    def _call_specialist(self, name: str, task: str, context: str = "") -> AgentResult:
        agent = self._make_specialist(name)
        result = agent.run(task=task, context=context)
        self._specialist_results.append(result)
        return result

    def _plan_node(self, state: GraphState) -> GraphState:
        task = state["task"]
        mem_summary = self.memory.summary()

        planner_prompt = (
            "You are planning specialist work for a software engineering supervisor. "
            "Return JSON only: {\"calls\": [{\"specialist\": str, \"task\": str, "
            "\"context\": str, \"group\": int}]}. "
            "Rules: use only these specialists: "
            f"{', '.join(SPECIALIST_NAMES)}. "
            "Use group numbers so calls in the same group are independent and can run in parallel. "
            "Keep between 1 and 6 calls."
        )

        user_prompt = (
            f"TASK:\n{task}\n\n"
            f"EXISTING MEMORY:\n{mem_summary}\n\n"
            "Plan the work now."
        )

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=planner_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text_chunks: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_chunks.append(block.text)
        raw = "\n".join(text_chunks).strip()

        calls: list[PlannedCall]
        try:
            data = json.loads(raw)
            parsed = data.get("calls", [])
            calls = [
                PlannedCall(
                    specialist=str(c["specialist"]),
                    task=str(c["task"]),
                    context=str(c.get("context", "")),
                    group=int(c.get("group", 0)),
                )
                for c in parsed
                if str(c.get("specialist", "")) in SPECIALIST_REGISTRY and str(c.get("task", "")).strip()
            ]
        except Exception:
            calls = []

        if not calls:
            calls = [
                PlannedCall(
                    specialist="fullstack",
                    task=f"Deliver an end-to-end implementation plan and starter code for: {task}",
                    context="Fallback plan because planner output was not parseable JSON.",
                    group=0,
                )
            ]

        if self.verbose:
            LOGGER.info("[LANGGRAPH][PLAN] %s", [f"{c.specialist}@g{c.group}" for c in calls])

        self.memory.write(
            "decisions.langgraph.plan",
            json.dumps([c.__dict__ for c in calls], indent=2),
            agent="supervisor",
            summary="LangGraph orchestration plan",
        )

        return {"plan": [c.__dict__ for c in calls]}

    def _execute_node(self, state: GraphState) -> GraphState:
        raw_plan = state.get("plan", [])
        calls = [
            PlannedCall(
                specialist=str(c["specialist"]),
                task=str(c["task"]),
                context=str(c.get("context", "")),
                group=int(c.get("group", 0)),
            )
            for c in raw_plan
            if str(c.get("specialist", "")) in SPECIALIST_REGISTRY
        ]

        grouped: dict[int, list[PlannedCall]] = {}
        for call in calls:
            grouped.setdefault(call.group, []).append(call)

        outputs: list[dict[str, Any]] = []
        for group_id in sorted(grouped):
            batch = grouped[group_id]
            if self.verbose:
                LOGGER.info("[LANGGRAPH][EXECUTE] group=%s specialists=%s", group_id, [c.specialist for c in batch])

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                futures = {
                    pool.submit(self._call_specialist, c.specialist, c.task, c.context): c
                    for c in batch
                }
                for fut in concurrent.futures.as_completed(futures):
                    c = futures[fut]
                    try:
                        r = fut.result()
                    except Exception as exc:
                        r = AgentResult(
                            specialist=c.specialist,
                            task=c.task,
                            output=f"ERROR: {exc}",
                            success=False,
                            error=str(exc),
                        )
                        self._specialist_results.append(r)
                    outputs.append(
                        {
                            "group": group_id,
                            "specialist": r.specialist,
                            "task": r.task,
                            "output": r.output,
                            "files_written": r.files_written,
                            "memory_keys": r.memory_keys_written,
                            "messages_sent": r.messages_sent,
                            "success": r.success,
                            "error": r.error,
                        }
                    )

        return {"specialist_results": outputs}

    def _synthesize_node(self, state: GraphState) -> GraphState:
        task = state["task"]
        results = state.get("specialist_results", [])
        mem_summary = self.memory.summary()
        bus_summary = self.bus.summary()

        synthesis_prompt = (
            "You are a senior engineering supervisor. Synthesize a final report from specialist outputs. "
            "Include: 1) what was built, 2) key decisions, 3) risks/open issues, 4) next steps."
        )
        user_prompt = (
            f"TASK:\n{task}\n\n"
            f"SPECIALIST RESULTS (JSON):\n{json.dumps(results, indent=2)}\n\n"
            f"SHARED MEMORY SUMMARY:\n{mem_summary}\n\n"
            f"MESSAGE BUS SUMMARY:\n{bus_summary}"
        )

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=synthesis_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text_chunks: list[str] = []
        for block in response.content:
            if hasattr(block, "text"):
                text_chunks.append(block.text)
        final_output = "\n".join(text_chunks).strip() or "No synthesis output produced."

        self.memory.write(
            "artifacts.supervisor.final_report",
            final_output,
            agent="supervisor",
            summary="Final synthesized report from LangGraph supervisor",
        )

        return {"final_output": final_output}

    def run(self, task: str) -> SupervisorResult:
        if self.verbose:
            LOGGER.info("[LANGGRAPH][SUPERVISOR] %s", task[:80])

        state = self._graph.invoke({"task": task})

        sr = SupervisorResult(task=task)
        sr.final_output = state.get("final_output", "No final output produced.")
        sr.specialist_results = self._specialist_results
        sr.total_files = [f for r in self._specialist_results for f in r.files_written]
        sr.memory_snapshot = self.memory.snapshot()
        sr.message_log = [m.to_dict() for m in self.bus.all_messages()]
        sr.success = all(r.success for r in self._specialist_results) if self._specialist_results else True
        return sr
