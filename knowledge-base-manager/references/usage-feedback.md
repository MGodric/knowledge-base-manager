# Usage feedback

This reference defines the lightweight, event-triggered mechanism for recording
concrete operational issues observed during knowledge-base tasks.

Do not load this reference or record feedback during normal, problem-free tasks.
Problem-free runs do not produce feedback reports, background evaluations, or
feedback-dedicated audits; normal post-write audits and checks required by the
underlying task (such as Promote or Move) proceed as usual.

## F1. Trigger criteria

Record feedback **only** when a concrete failure is actually observed during an
ongoing authorized task.

| Category | Triggering observation | Non-triggering situations |
| --- | --- | --- |
| **Retrieval omission** | A subsequent step or user pointer reveals an existing entry that should have matched the original query. | Empty search results when it is unknown whether a relevant entry exists. |
| **Reading misuse** | An answer omitted necessary conditions or cited obsolete conclusions, with verifiable correction basis; user-flagged defects may be retained as `to-verify`. | Mere suspicion or subjective impression that an entry "might be hard to read". |
| **Update omission** | After updating or moving an entry, another entry is found retaining affected obsolete statements. | Merely finding inbound links without evidence that the referenced content is invalid or needs changing. |
| **Tooling or operational failure** | A script or command fails, produces incorrect results, or encounters excessive blocking delays that impede work. | Hypothetical concerns about future scale or speculative performance worries. |

### Operational priorities

1. **Complete the authorized task first**: Do not derail or halt the user's
   primary request to investigate feedback.
2. **Record observations, not speculations**: Note the concrete symptom. If the
   root cause is uncertain, mark it as `to-verify` (`待核实`). Do not launch
   unauthorized investigations solely to determine causes.
3. **No automatic repair**: Feedback recording records observations only; it
   does **not** authorize fixing, merging, batch updating, or adding new
   associations to knowledge-base entries.

## F2. Anchor and short record format

Feedback records must be locatable and compact.

### Anchor principles

- **Reuse existing identifiers**: Use entry ID, relative path within the
  knowledge base (e.g. `content/knowledge/auth.md`), or section heading.
- **Auxiliary line numbers**: Line numbers may be included to assist navigation,
  but are secondary since line numbers shift over time.
- **Minimal reproduction snippet**: For tooling errors or query omissions,
  include the exact search term, failed command, or short error message.
- **No schema burden**: Do not add new mandatory frontmatter fields, tags, or
  permanent paragraph IDs across knowledge-base entries to support feedback.

### Record fields

A record contains only the essential fields:

```markdown
- **Date**: YYYY-MM-DD
- **Task / Context**: Brief description of the current task
- **Category**: Retrieval omission | Reading misuse | Update omission | Tooling failure
- **Anchor**: Entry ID, relative path, or section heading
- **Observation**: Concrete symptom observed
- **Disposition / To-Verify**: Next step, open question, or mark as `to-verify`
```

Follow the conversation's language. Keep the note concise so it can be
re-located later. Never copy entire conversation transcripts, token logs, or
runtime timing dumps.

## F3. Workflow cost and isolation

- **Zero overhead when untriggered**: When no issue occurs, do not load this
  reference, produce feedback reports, or add feedback-related checks.
- **Strictly bounded feedback overhead**: Even when an issue is observed, never
  introduce full-library scans, source-material rereading, additional model
  evaluations, or reviewer agents solely for feedback. This restriction governs
  work newly introduced for feedback; it does not impede the reading, audit,
  verification, or review already required by the underlying task, nor does it
  prevent rereading the feedback destination file for safe writing.
- **Preserve existing isolation gates**: Feedback is recorded by the active
  agent without disrupting the designated-editor write gate.
- **Severity over frequency**: A single concrete, verifiable issue is sufficient
  to record; do not require multiple occurrences.

## F4. Destination and authorization

- **Explicit sink required**: Feedback may only be written to an explicitly
  authorized feedback file (such as a configured local convention in project
  instructions).
- **Fallback to task report**: If no feedback sink is configured, or if the
  configured target is inaccessible or unconfirmed, include the short record in
  the task completion report. Do not guess paths, scan drives, or block the task
  to ask the user for a path.
- **Local development data**: A feedback file in a local development directory
  outside the knowledge base is development data, not a knowledge-base entry; the
  active agent may update it directly.
- **Knowledge-base sink constraints**: If a feedback destination is configured
  inside a knowledge base, it remains subject to normal knowledge-base write
  authorization and designated-editor rules.

## F5. Privacy and retention

- **Minimal data**: Record only locators and necessary descriptions. Never
  persist secrets, credentials, personal data, or full file contents.
- **Re-read before write**: Before writing to a feedback file, re-read the
  target. If the exact same issue is already recorded, append details or update
  the existing note rather than duplicating entries.
- **Concurrency and conflicts**: Do not overwrite changes from other sessions. If
  safe writing cannot be guaranteed, report the observation in the task output.
- **No silent closure**: Do not automatically close or remove unresolved
  observations without explicit verification or user instruction.
