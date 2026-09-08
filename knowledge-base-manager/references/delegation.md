# Delegated knowledge-base writes

Use one subagent as the designated editor for every write mode when subagent orchestration is available. This is a mandatory write gate: the primary agent must delegate before detailed source reading, drafting, staging, or mutation. It keeps detailed note reading and editing out of the main session while retaining authorization and verification there.

If the current handoff contains `KB_EDITOR_ROLE: designated`, this agent is already the editor. It must execute the bounded write directly and must not delegate again.

## Division of responsibility

The main agent must:

1. Resolve the exact absolute knowledge-base root and remove any ambiguity before delegation.
2. Determine the authorized operation, minimal authorized source-path list, scope, sensitive-content and publication boundary, irreversible choices, and acceptance criteria without reading all source bodies into the main context. For semantic work, carry forward the reader, purpose, important questions, and any conclusions already settled by the user or source owner. Let the editor perform bounded expert explanation and evidence analysis, refine the questions after source reading, and choose the entry decomposition. Do not preselect an exact number of entries unless the user explicitly requires that count.
3. Spawn the editor before any knowledge entry is drafted or staged. Use an isolated handoff (`fork_turns: "none"`) unless a small recent-turn window is necessary.
4. Send a minimal, self-contained handoff rather than the entire conversation when possible.
5. Wait for the editor to finish, then re-read the actual modified blocks rather than accepting its summary. Check every acceptance field and claimed count, inspect its reported paths, and independently run or verify the final audit. Prefer one 120-180 second wait; inspect agent state only after a timeout or attention event instead of polling repeatedly at short intervals.
6. Report files changed, audit result, unresolved issues, and model routing accurately. If only the requested override is observable, say `requested model/reasoning`; call it `effective` only when the runtime exposes confirmation.

The confirmed absolute root must be present in every handoff; a subagent must not infer it from the parent conversation or a bare folder name.

The designated editor must:

1. Treat `KB_EDITOR_ROLE: designated` as the recursion guard and explicitly use `$knowledge-base-manager` with the exact root supplied in the handoff.
2. Re-read source and target files before editing and apply the relevant workflow and safety reference. For semantic promotion, inventory material topics first and choose the complete set of distinct durable entries only after reading the authorized sources.
3. Stay inside the authorized root and operation scope.
4. Run `kb-audit.ps1` after writes and return a compact change manifest. For Promote and Project Synthesis, include the existing coverage ledger mapping reader questions and material source topics to actual answers, project-summary-only treatment, or a reasoned gap/deferral. Capture and mechanical writes do not require this ledger or synthesis review.
5. Not spawn or delegate to another agent.

Because agents share the same filesystem, the editor changes the real target files. The main agent must not recreate the same edits.

## Additional independent review for Project Synthesis

For a Project Synthesis, the main agent re-reads the editor's actual changes
and performs the basic independent acceptance check already required above. A
low-risk synthesis needs no second reviewer.

Request one additional read-only independent reviewer for material technical
conclusions, root-cause claims, substantive SOP changes, decisions, conflicts,
important inferences promoted from observations, or safety, legal, medical,
financial, or administrative-eligibility content. This reviewer is not a
designated editor: it must not edit files, expand the approved sources or
permissions, or delegate. It reviews the stated scope, evidence boundary,
provenance, and actual written result against the reader questions and source
coverage. Apply [content acceptance](knowledge-writing.md#content-acceptance),
including whether the explanation works without reconstructing it from sources,
then return only
`PASS`, `FIX`, or `BLOCKED` with concise reasons.

The original designated editor addresses `FIX`; the main agent re-reads the
repair and performs final acceptance. Do not impose a fixed retry count: each
retry must address a specific reported defect or missing answer. If the main
agent replaces the editor, changes its model route, or transfers the repair to
another editor, it must first stop the old editor and preserve the unaccepted
draft for inspection; never run two writers against the same target. If
independent review is unavailable and the main agent cannot reliably perform
the needed check, return `BLOCKED` and
ask the user for direction. Keep the designated-editor recursion guard.

For a sustainable synthesis batch, assign reviewers by distinct substantive
risk clusters, not one reviewer per ordinary entry. The primary agent handles
the basic check for ordinary entries. Add an independent reviewer only when a
cluster contains a material technical conclusion, root-cause claim,
substantive SOP change, decision, conflict, important inference, or high-risk
subject; separate reviewers are justified only for materially different such
clusters.

## Model and reasoning route

Choose and record the requested model and reasoning effort for every editor and
reviewer. Route by the judgment the delegated task still requires, not by a
blanket rule for all semantic work.

Use this decision boundary before spawning:

- **Answer already determined:** the handoff or authorized sources provide the
  material conclusion and its controlling conditions, and the editor only has
  to express, organize, deduplicate, or place it. Ordinary judgment about
  wording and entry decomposition does not make the answer unresolved.
- **Key knowledge judgment remains:** the editor must derive a material answer,
  explain a mechanism that is not already established, synthesize multiple
  sources, distinguish conflicting claims, determine controlling conditions or
  exceptions, or assign an evidence boundary or epistemic status that affects
  the conclusion.

### Mechanical writes

Use `gpt-5.6-luna` with `medium` reasoning by default for bounded work whose semantic decisions are already supplied:

- capture from a clear payload;
- initialize an exact confirmed empty root;
- apply an approved move or rename mapping;
- update known links mechanically;
- run and report an audit or apply an unambiguous repair.

Raise Luna to `high` only when the mechanical operation is unusually large or requires careful preservation.

### Semantic organization

When the answer is already determined and the sources are clear, route ordinary
promotion, deduplication, taxonomy, and explanatory organization one model tier
below the main model by default. Choose `medium` reasoning for direct material
and `high` only when density or preservation difficulty warrants it:

| Main model | Editor model |
|---|---|
| `gpt-5.6-sol` | `gpt-5.6-terra` |
| `gpt-5.6-terra` | `gpt-5.6-luna` |
| `gpt-5.6-luna` | `gpt-5.6-luna` |

Thus a `sol` main session normally routes already-determined semantic
organization to `terra`; use `high` reasoning only when that settled material
is unusually dense or difficult to preserve. A simple capture still routes to
`luna medium`.

### Key knowledge judgment

When key knowledge judgment remains, prefer the same model as the main session
and do not use a lower model tier by default. Choose reasoning sufficient for
the task and normally match the main session's effort. Keep the isolated
designated-editor handoff: the editor may read the authorized sources, compare
evidence, and produce the expert explanation without requiring the main agent
to read every source first.

The main agent still owns authorization, source and operation scope,
sensitive-content and publication decisions, irreversible choices, and final
acceptance. A delegated evidence analysis does not expand authorized sources or
decide whether sensitive material may be retained or published.

Do not assign an editor or reviewer a stronger model tier than the main session
unless the user has authorized it or the main agent records a concrete reason.
There is an additional cost gate for the highest model tier currently available
in the runtime: any initial classification or later reclassification that would
dispatch an editor or reviewer at that tier counts as an upgrade for this gate,
including same-tier routing from a highest-tier main session. It cannot be
treated as a routine same-tier choice. Before dispatch, the main agent must tell
the user the trigger, requested model and reasoning effort, bounded task scope,
and expected increase in cost. If token usage cannot be estimated
reliably, say that it is unknown. Start that highest-tier work only after the
user explicitly agrees; a prior explicit authorization for the same task and
route may be reused, but general task authorization is insufficient. While
waiting, continue only work that does not depend on the proposed upgrade. This
does not add approval to an ordinary route that remains below that tier.

If an editor discovers a material contradiction, cannot explain a mechanism
needed for a core answer, or repeatedly misses a core reader question, it must
stop and return the exact gap, relevant source locators, and why the current
route is insufficient. It must not spawn a replacement. The main agent then
reclassifies the bounded task and either re-dispatches it under these routing
and single-writer rules or records a gap. Missing source evidence cannot be
repaired by a stronger model and must remain an explicit gap or blocker.

For a complex Project Synthesis that requires an independent reviewer, use a
reviewer whose model tier is at least the editor's and whose reasoning effort is
adequate for the same evidence boundary; normally use the same model and
reasoning as the editor. The reviewer remains read-only and returns only the
existing `PASS`, `FIX`, or `BLOCKED` result. A low-risk synthesis still needs no
additional reviewer.

For an unknown main model, use Luna for mechanical work, a lower-cost capable
model for ordinary semantic organization whose answer is already determined,
and the same model as the main session for key knowledge judgment. Do not treat
all semantic work as eligible for a downgrade.

Treat this routing as the skill's cost-control policy, not as an automatic Codex
default. If a preferred override is unavailable, report that fact. For
mechanical or already-determined organization, use the nearest suitable
available fallback and report it. Never silently downgrade key knowledge
judgment; obtain an authorized suitable editor route, use main-session writing
only after the explicit fallback approval required below, or return `BLOCKED`.

## Context isolation

Prefer an isolated spawn with no inherited turns and include only:

- `KB_EDITOR_ROLE: designated`;
- exact knowledge-base root;
- operation and acceptance criteria;
- exact source files or a concise factual payload;
- for semantic work, the intended reader and prior knowledge, practical or explanatory purpose, important questions, and concrete details to retain; pass known gaps and the source-reading scope, including whether referenced attachments are authorized;
- for semantic work, permission to refine questions and determine entry decomposition after reading authorized sources rather than a parent-imposed count;
- for a synthesis batch, the one-time metadata manifest fields, top-*k*
  duplicate-body limit with ambiguity-only expansion, and each parent page that
  may be updated once;
- language and local note conventions;
- allowed and forbidden paths;
- required provenance fields (including literal `verified` and revision/version-state tokens for formal project-derived entries), audit command, and response fields; include the coverage ledger only for semantic work;
- the instruction that this agent is the final editor and must not delegate.

Keep durable-body requirements separate from completion-report requirements.
A request for a short reply governs the report, not the depth of the stored
explanation, unless the user explicitly asks for a short entry. Do not pass
unrelated conversational brevity preferences as article constraints.

The editor's completion report must name the effective model and reasoning effort when observable, otherwise the requested route and that it is unconfirmed; it must also name every changed path, audit error/warning counts, and unresolved or deliberately deferred topics. It must derive field-presence claims by re-reading the written files, not from the handoff or intended template. For semantic work, the coverage ledger locates answers for human review; the primary must inspect them. Neither a filled ledger nor structural audit success establishes content completeness.

If a self-contained handoff would lose essential nuance from recent conversation, pass the smallest supported recent-turn window instead of the full history.

## Fallback

If no subagent capability is available or spawning fails, announce that isolation cannot be applied and stop before detailed source reading or writes. Ask whether the user authorizes a main-session fallback. Only after explicit approval may the primary agent complete the bounded edit directly using the same minimal-read and audit rules. Never silently pretend delegation occurred.
