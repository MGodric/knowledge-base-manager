# Delegated knowledge-base writes

For every write mode, the primary agent must spawn one isolated designated editor before detailed source reading, drafting, staging, or mutation. If subagents are unavailable, follow [Fallback](#fallback). A handoff containing `KB_EDITOR_ROLE: designated` identifies the editor and forbids further delegation. In a Gemini dual-model task, that editor remains read-only until the primary starts the write phase after comparing both analyses.

## Division of responsibility

The main agent must:

1. Resolve the exact absolute knowledge-base root; authorize the operation, minimal source list, sensitive-content and publication boundary, irreversible choices, and acceptance criteria. For semantic work, pass the reader, purpose, important questions, and already-settled conclusions without reading all source bodies into the main context.
2. Spawn the editor with a minimal self-contained handoff, preferably `fork_turns: "none"`. Let it analyze authorized sources and choose the entry decomposition; do not impose an entry count unless the user did.
3. Re-read the actual changed blocks, check acceptance fields and claims, and independently run or verify the final audit. Report changed paths, audit results, gaps, and the requested model/effort; call them effective only if the host confirms them.

The designated editor must:

1. Use `$knowledge-base-manager` with the exact root supplied in the handoff; never infer it or delegate again.
2. Re-read sources and targets before editing, stay within the authorized scope, and apply the relevant workflow and safety rules. For semantic promotion, inventory material topics before deciding entries.
3. After writing, run `python -X utf8 ./scripts/kb.py audit` and return changed paths, audit counts, and unresolved topics. Promote and Project Synthesis also require the coverage ledger; Capture and mechanical writes do not.

Agents share a filesystem: only the designated editor changes the real target, and the primary does not recreate those edits.

## Additional independent review for Project Synthesis

The primary always re-reads the written result. Add a separate read-only reviewer for Project Synthesis with material technical conclusions, root-cause claims, substantive SOP changes, decisions, conflicts, important inferences, or safety, legal, medical, financial, or administrative-eligibility content. Low-risk synthesis needs no second reviewer; batch reviewers by substantive risk cluster.

The reviewer checks the actual result, authorized sources, provenance, reader questions, and [content acceptance](knowledge-writing.md#content-acceptance), then returns `PASS`, `FIX`, or `BLOCKED` with reasons. It cannot edit, delegate, or expand scope. The original editor addresses `FIX`; the primary re-reads the repair. Before replacing an editor, stop the old writer and preserve its draft. If review is unavailable and the primary cannot reliably check the result, return `BLOCKED` and ask for direction.

## Model and reasoning route

Choose the Codex or Gemini route from the actual host; model catalogs do not prove host availability. Classify the judgment still required:

| Class | Decision boundary |
| --- | --- |
| M — mechanical | Conclusion, target, and method are supplied, as in clear Capture, approved path mapping, or unambiguous repair. |
| S — settled answer | Authorized material supplies every substantive conclusion and condition; the editor only organizes or expresses it. Do not assume unread sources settle the answer. |
| J — knowledge judgment | The editor must derive a conclusion, explain an unestablished mechanism, synthesize sources, resolve conflicts, or set controlling conditions or evidence status. Uncertain classification is J. |

The primary retains authorization, scope, privacy, publication, and acceptance decisions. Stronger models cannot fill missing source evidence. An editor finding a material conflict or missing core answer stops and returns source locators; the primary reclassifies or records the gap. Only the primary may replace an editor, after stopping the old writer.

### Codex model route

This registry defines **same-family order only**. Intersect it with the delegation tool's exact available IDs and supported efforts; do not infer availability, a new family's order, or cross-family rank.

| Main-session family | Low → high exact IDs |
| --- | --- |
| GPT-6 | `gpt-6-luna` → `gpt-6-sol` → `gpt-6-astra` |
| GPT-5.6 compatibility | `gpt-5.6-luna` → `gpt-5.6-terra` → `gpt-5.6-sol` |

1. Require `medium` effort for M/S unless the user explicitly records a lower task-specific exception. J requires at least `high` and the observable main-session effort; an unknown main effort blocks J.
2. Honor a user's task-specific exact model or effort; compute only unspecified fields and verify the combination. A stronger or cross-family choice needs the user's instruction or a recorded concrete reason. Any effort below its class floor needs an explicit user exception.
3. First remove candidates with unsupported or unknown effort support. Without a model override, M chooses the lowest remaining same-family tier no stronger than the main model; S tries only the immediately lower tier, then the main model if that tier was removed; J uses the main model. If the selected model is ineligible, return `BLOCKED`. Never skip two tiers or silently lower J.
4. A required independent reviewer must be at least as capable as the editor and inspect the written result; normally use the editor's exact model and effort. If that route is unavailable, return `BLOCKED` rather than silently choosing a weaker reviewer. If review needs stronger judgment, reclassify the task and recheck the cost gate.
5. Before dispatching an editor or reviewer at the highest currently available registered tier in this family, including the main model at that tier, state the trigger, exact route, bounded scope, and extra cost (or “unknown”). Obtain task-specific consent; reuse only consent for the same task and route.
6. Record classification, host candidates, requested route, consent, and effective values when reported. Stop on runtime rejection. If an exact override is accepted but only the request is observable, report “requested, unconfirmed.” If the host may silently change it and cannot reveal the actual route, return `BLOCKED` before writing.

Unknown main ID, unreviewed family, missing availability, or unsupported effort blocks automatic routing. An explicit cross-family route still needs a comparable J capability and adequate review. Never use `latest` aliases. This policy applies to this Skill, not all Codex tasks.

### Gemini model route

**Ordinary route.** Preserve the session/project's exact Gemini model and observable reasoning setting; do not change Flash versions or map Pro to another version. If neither its exact ID nor guaranteed same-model inheritance can be verified, return `BLOCKED`. Honor a user's task-specific model change after availability and quality checks; never apply the Codex registry. For a delegated model that the host identifies as its highest tier, obtain the existing task-specific cost consent. If tier metadata is absent, disclose that uncertainty and obtain cost consent rather than inferring rank from `Flash` or `Pro`.

**Difficult-task trigger.** Ask about a dual route only for J plus at least one of: material conflict in authorized sources; a new multi-step derivation, proof, or root-cause judgment affecting the core answer; a high-impact safety, legal, medical, financial, or administrative-eligibility conclusion; or inability of the primary to check the core answer reliably. Length, formula count, or a newer Flash alone does not qualify. If discovered mid-task, stop before expanding the route.

**Preflight and choice.** Verify that the host can dispatch one exact Flash ID and one exact Pro ID concurrently and, for writes, resume the same editor after analysis. The current Flash/Pro model remains its arm; choose the other from host-confirmed IDs. If the current model is neither, dual work needs a separate user-selected exact Flash/Pro model, which becomes this task's editor model; do not claim the old model was retained. Let the user choose when several IDs are available. If any prerequisite fails, report the dual route unavailable and keep the authorized single-model route.

Ask once whether to **keep the current single model** or **run Flash + Pro in parallel**. Give the D trigger, both exact IDs, shared authorized sources, read-only analysis scope, extra cost or “unknown,” and any later sole editor and post-write reviewer. Disclose highest-tier status when known; if unknown, include that uncertainty in the cost request. Only explicit consent to this task, combination, and scope starts both arms. Silence permits only unrelated read-only preparation. A single-model choice keeps existing review gates; missing mandatory review remains `BLOCKED`.

**Execution.** For a dual write, designate the task's selected-model agent with `KB_EDITOR_ROLE: designated` before detailed reading; it remains read-only through analysis. For a read-only task, neither arm is an editor. The isolated Flash and Pro arms concurrently read the same minimal sources without seeing each other's output or changing files or shared drafts. Each returns claims, source locators, reasoning, conditions, uncertainty, and proposed organization. Report failed concurrency; never describe serial work or two Flash arms as Flash + Pro parallel work.

The primary checks differences against authorized sources; model agreement is not evidence, and unresolved conflicts remain visible or block the conclusion. A read-only task ends with the checked answer. In a write task, only the designated editor writes after receiving the checked comparison. Earlier analysis does not count as post-write review: if Project Synthesis needs one, a separate reviewer must inspect the result with capability at least equal to the editor's. A prior Pro analyst may later review a Flash editor; a Flash analyst does not automatically qualify to review a Pro editor. If required review is unavailable, return `BLOCKED`. The primary re-reads the files and verifies the audit. This stricter reviewer gate applies only to Gemini dual writes; the single-model review fallback above remains.

## Context isolation

Prefer `fork_turns: "none"`. Give the editor `KB_EDITOR_ROLE: designated`, exact root, operation, acceptance criteria, minimal sources, allowed and forbidden paths, language/conventions, provenance fields (including `verified` and revision/version-state for formal project entries), and audit/report requirements. For semantic work, also give reader, purpose, questions, known conclusions and gaps, attachment scope, permission to refine entry decomposition, and the coverage-ledger requirement. For a synthesis batch, give its one-time metadata manifest, duplicate-body limit, and allowed parent-page updates. Pass a small recent-turn window only when a self-contained handoff would lose essential nuance.

A short completion report does not imply a short knowledge entry. The editor reports changed paths, audit counts, unresolved topics, and effective model/effort when observable, otherwise requested and unconfirmed. It verifies field claims by re-reading files. The primary inspects the coverage ledger and actual content; neither the ledger nor a clean audit proves completeness.

## Fallback

If spawning is unavailable or fails, stop before detailed source reading or writing. Explain the loss of isolation and obtain explicit user approval for a main-session fallback. Then apply the same scope and audit rules; never claim delegation occurred.
