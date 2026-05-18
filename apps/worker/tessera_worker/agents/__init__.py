"""Persona agents (Phase B).

One module per persona implementing the system-prompt + LLM call pipeline.
Each loads its spec from `personalities.md`, screens with Haiku, writes with
Sonnet, validates with Pydantic, persists to `analyst_reports`.

Planned (Phase B):
- runner.py      Orchestrates the desk: schedules all personas, fan-out + collect
- prompt.py      Assembles system prompt from persona spec + features + memory
- screen.py      Universe screen (Haiku 4.5) + hybrid mechanical metric union
- thesis.py      Deep thesis (Sonnet 4.6) on shortlist
- validate.py    Pydantic + citation + universe checks; reject + log on fail
- chat.py        Chat-with-analyst endpoint (per-turn prompt assembly + SSE)
"""
