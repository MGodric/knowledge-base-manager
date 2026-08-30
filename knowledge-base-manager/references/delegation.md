# Delegated knowledge-base writes

Use one subagent as the designated editor for every write mode when subagent orchestration is available. This is a mandatory write gate: the primary agent must delegate before detailed source reading, drafting, staging, or mutation. It keeps detailed note reading and editing out of the main session while retaining authorization and verification there.

If the current handoff contains `KB_EDITOR_ROLE: designated`, this agent is already the editor. It must execute the bounded write directly and must not delegate again.

## Division of responsibility

The main agent must:

1. Resolve the exact absolute knowledge-base root and remove any ambiguity before delegation.
2. Determine the authorized operation, a minimal source-path list, sensitive-data boundary, and acceptance criteria without reading all source bodies into the main context. Do not preselect an exact number of entries unless the user explicitly requires that count.
3. Spawn the editor before any knowledge entry is drafted or staged. Use an isolated handoff (`fork_turns: "none"`) unless a small recent-turn window is necessary.
4. Send a minimal, self-contained handoff rather than the entire conversation when possible.
5. Wait for the editor to finish, then re-read the actual modified blocks rather than accepting its summary. Check every acceptance field and claimed count, inspect its reported paths, and independently run or verify the final audit. Prefer one 120-180 second wait; inspect agent state only after a timeout or attention event instead of polling repeatedly at short intervals.
6. Report files changed, audit result, unresolved issues, and model routing accurately. If only the requested override is observable, say `requested model/reasoning`; call it `effective` only when the runtime exposes confirmation.

The confirmed absolute root must be present in every handoff; a subagent must not infer it from the parent conversation or a bare folder name.

The designated editor must:

1. Treat `KB_EDITOR_ROLE: designated` as the recursion guard and explicitly use `$knowledge-base-manager` with the exact root supplied in the handoff.
2. Re-read source and target files before editing and apply the relevant workflow and safety reference. For semantic promotion, inventory material topics first and choose the complete set of distinct durable entries only after reading the authorized sources.
3. Stay inside the authorized root and operation scope.
4. Run `kb-audit.ps1` after writes and return a compact change manifest plus a coverage ledger mapping each material source topic to a formal entry, project-summary-only treatment, or deliberate deferral with a reason.
5. Not spawn or delegate to another agent.

Because agents share the same filesystem, the editor changes the real target files. The main agent must not recreate the same edits.

## Model and reasoning route

Choose the editor model by the delegated task, not only by the main model.

### Mechanical writes

Use `gpt-5.6-luna` with `medium` reasoning by default for bounded work whose semantic decisions are already supplied:

- capture from a clear payload;
- initialize an exact confirmed empty root;
- apply an approved move or rename mapping;
- update known links mechanically;
- run and report an audit or apply an unambiguous repair.

Raise Luna to `high` only when the mechanical operation is unusually large or requires careful preservation.

### Semantic organization

For promotion, deduplication, taxonomy decisions, or synthesis across multiple notes, prefer one tier below the main model and use reasoning up to `high`:

| Main model | Editor model |
|---|---|
| `gpt-5.6-sol` | `gpt-5.6-terra` |
| `gpt-5.6-terra` | `gpt-5.6-luna` |
| `gpt-5.6-luna` | `gpt-5.6-luna` |

Thus `sol high` normally routes semantic organization to `terra high`, while a simple capture from the same session routes to `luna medium`.

### High-stakes judgment

Keep conflict resolution, evidence-boundary decisions, sensitive-content decisions, and irreversible migration choices in the main session. After the main agent and user settle the decision, delegate only the bounded execution. Do not lower the model tier for unresolved judgment merely to save usage.

For an unknown main model, use Luna for mechanical work and the nearest available lower-cost capable model for semantic organization. Treat this routing as the skill's cost-control policy, not as an automatic Codex default. If the preferred override is unavailable, use the nearest suitable available model and report the fallback.

## Context isolation

Prefer an isolated spawn with no inherited turns and include only:

- `KB_EDITOR_ROLE: designated`;
- exact knowledge-base root;
- operation and acceptance criteria;
- exact source files or a concise factual payload;
- for semantic work, permission to determine entry decomposition after source inventory rather than a parent-imposed count;
- language and local note conventions;
- allowed and forbidden paths;
- required provenance fields (including literal `verified` and revision/version-state tokens), coverage ledger, audit command, and response fields;
- the instruction that this agent is the final editor and must not delegate.

The editor's completion report must name the effective model and reasoning effort when observable, otherwise the requested route and that it is unconfirmed; it must also name every changed path, audit error/warning counts, and unresolved or deliberately deferred topics. It must derive field-presence claims by re-reading the written files, not from the handoff or intended template. Structural audit success does not establish semantic completeness; the coverage ledger is the human-reviewable completeness check.

If a self-contained handoff would lose essential nuance from recent conversation, pass the smallest supported recent-turn window instead of the full history.

## Fallback

If no subagent capability is available or spawning fails, announce that isolation cannot be applied and stop before detailed source reading or writes. Ask whether the user authorizes a main-session fallback. Only after explicit approval may the primary agent complete the bounded edit directly using the same minimal-read and audit rules. Never silently pretend delegation occurred.
