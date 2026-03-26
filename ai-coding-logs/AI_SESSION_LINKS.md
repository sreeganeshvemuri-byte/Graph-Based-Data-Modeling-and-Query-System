# AI Coding Session Links

These are the AI tool sessions used to build the O2C Graph-Based Data Modeling and Query System.

---

## 1. Runable — Final Integration, Revamping, Testing & Deployment
**Link:** https://runable.com/chat/0c4de663-5340-4c38-8404-3ecb657426c0

Used for: Complete system integration, UI redesign (clean white theme, dot-graph, floating tooltips), query engine full rewrite (dynamic SQL + schema RAG), SSE streaming, node highlighting with camera animation, conversation memory with pronoun resolution, rate limit handling (model cascade across 5 models), graph view selector (Core / Orders / Billing / Full), metadata fixes for all node types, deployment to Cloudflare D1 + Workers.

---

## 2. Claude Code — Backend Logic & Search Engine
**Link:** https://claude.ai/share/f237c3ed-0be4-4ad0-b25f-456a04b9ab43

Used for: Backend architecture decisions, SQLAlchemy ORM models, JSONL ingestion pipeline, graph edge builder, query handlers (trace_flow, top_products, broken_flows), Pydantic validation layer, LLM planner design.

---

## 3. ChatGPT — Initial Planning
**Link:** https://chatgpt.com/share/69c56e9c-a608-8324-8077-c8bebe6ff36a

Used for: Task planning, understanding the O2C domain, deciding on tech stack (FastAPI + SQLite + React + Cytoscape.js), initial architecture diagram, dataset analysis strategy.

---

## 4. Cursor — Initial Full-Stack Implementation
**File:** `cursor_graph_based_data_modeling_platform.md` (in this folder)

Used for: Step-by-step implementation of the initial full-stack system — backend API routes, database models, ingestion scripts, and initial frontend components.
