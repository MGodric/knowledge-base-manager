# Writing useful knowledge

Read this reference for Promote and Project Synthesis, including substantive
rewrites of their results. Capture preserves supplied observations quickly;
it does not require a reader brief, coverage ledger, or synthesis review.

## Start with the reader's questions

Identify the intended reader, what they already know, and what they should be
able to understand, decide, or do after reading. Use the request and project
context; ask only when a material ambiguity remains. The editor can refine the
questions while reading the authorized sources. Do not invent a new audience
that changes the user's task.

Use these questions to select and organize content, while still accounting for
important source topics. Reuse the workflow's coverage ledger for both: point
each question or topic to its answer in the resulting text, or to an explicit
gap/deferral and its consequence. This is a review aid, not a second record or
a mandatory table in the article.

Read enough relevant source material to answer the questions faithfully.
An overview may point to the detailed rule, derivation, result, or checklist;
follow that pointer when authorized. Source selection is not a requirement to
read every file in full. If an answer requires additional authorized material,
read it. If it requires access outside scope, name the missing answer and what
it prevents; do not fill the space with a generic reminder or invent a fact.

Factual content, parameters, hardware/chip specifics, APIs, and procedural steps
must be strictly grounded in authorized source materials. Pre-trained model
knowledge (parametric memory) may be used only for grammatical fluency,
structural formatting, and general conceptual clarity—never to extrapolate
unverified domain details, invent hypothetical behaviors, or guess unstated
implementation specifics. If the current knowledge base or authorized project
already contains relevant supplementary context, it may be selectively
incorporated, but must be explicitly marked with a provenance label (for example
`> 补充来源: [条目/项目名]` in Chinese, or `> Supplementary source: [entry/project]`
in English). Any question that cannot be answered from authorized materials or
labeled internal sources must be explicitly named as an open question or gap;
never fabricate an answer to make the entry feel complete.

## Classification dimensions

When organizing knowledge, distinguish four independent dimensions rather than
forcing entries into a rigid monolithic hierarchy:

| Dimension | Question Answered | Examples |
| --- | --- | --- |
| Subject domain | What field or topic is being studied or addressed? | Cryptography, backend systems, certification, administration |
| Source origin | Where did the raw material come from? | Research papers, courses, official manuals, debugging logs, experiments |
| Primary reading purpose | What should the reader be able to do after reading? | Understand sources, grasp concepts, execute tasks, evaluate conjectures, diagnose failures, choose options, understand a software project |
| Knowledge maturity | How well-supported is this understanding? | Sourced fact, mathematically proven, empirically tested, open conjecture, conflicting evidence |

Express maturity through natural language directly beside the relevant claims,
derivations, or code. Do not introduce mandatory frontmatter metadata or treat
`draft` versus `stable` as an indicator of mathematical or empirical proof strength.
Domain and source may overlap across entries; an entry is structured around its
primary reading purpose, with auxiliary modules added only as needed.

Keep three levels distinct: a primary purpose defines the article's task;
a scenario changes its emphasis (for example, administrative preparation versus
learning a framework); a local module supplies useful detail, such as a materials
checklist or a worked exercise. Choose content without turning these distinctions
into a mandatory classification form.

## Seven writing starting points

Choose an organizational structure based on the reader's primary goal. These
patterns provide an initial scaffolding, not mandatory headings or an audit checklist:

### 1. Literature & document interpretation
- **Reader question**: What problem did this source solve, and on what grounds does its conclusion hold?
- **Suggested flow**: Core problem & main conclusion → Essential background → Methodology & key arguments → Quantitative/qualitative results & boundary conditions → Author claims versus reader evaluation → Exact source locators.
- **Key discipline**: Faithfully preserve original evidential and argumentative logic. Do not blindly condense chapter by chapter. Distinguish the author's proven conclusions from the reader's personal extrapolations.

### 2. Knowledge explanation
- **Reader question**: What is this concept/mechanism, why does it work, and how is it applied?
- **Suggested flow**: Adapt the entry point to the audience: either begin with the formal question, definition, and deductive derivation (for theoretically grounded readers), or lead with an observable phenomenon, minimal concrete example, and intuitive puzzle (for practical/introductory readers). Then connect to mechanisms, boundary conditions, worked examples, and distractor/confusion analysis.
- **Key discipline**: For certification and exam preparation, ground test-point relevance in syllabus evidence or explicit past problems, rather than baseless "high frequency" claims. Explain why distractors fail conceptually; never reduce exam prep to superficial keyword tricks.

### 3. Practical guide & procedure
- **Reader question**: How do I accomplish a specific, concrete objective?
- **Suggested flow**: Objective & prerequisite checklist (with prerequisites, dependencies, and time windows) → Minimal end-to-end execution steps → Result verification checklist → Common branches and failure handling → Further operational pointers.
- **Key discipline**: For administrative procedures, enable readers to order their preparation sequence, calculate validity overlapping, and separate general institutional rules from individual case facts. For technical skills, ensure readers not only complete the steps but also understand the key mechanisms behind them.

### 4. Research exploration
- **Reader question**: Where does this conjecture or mechanism exploration currently stand?
- **Suggested flow**: Precise problem statement & current epistemic status → Formal definitions & core assumptions → Known verified results/lemmas → Key reasoning, experiments, or simulation setups → Meaningful failed paths & discarded hypotheses → Unresolved gaps & concrete next steps.
- **Key discipline**: Strictly distinguish mathematical proofs, exhaustive search bounds, empirical observations, and conjectures. Explicitly leave unproved logical gaps open rather than smoothing them over with plausible prose.

### 5. Problem diagnosis & experience
- **Reader question**: How do I recognize, diagnose, and resolve this issue or similar recurrences?
- **Suggested flow**: Observable symptoms & immediate effective workaround → Operating environment & exact trigger conditions → Diagnostic evidence & telemetry → Step-by-step troubleshooting attempts, observations, and discarded hypotheses → Root cause analysis → Recurrence prevention and recovery procedures.
- **Key discipline**: Preserve the chain of hypothesis, action, observation, and deduction. Never claim that a joint multi-variable change proves a single root cause. If full logs are needed, place them at the end.

### 6. Comparison and decision
- **Reader question**: Under these specific constraints, which option should be selected?
- **Suggested flow**: Decision context & framing → Hard constraints & evaluation criteria → Viable candidate options → Core trade-offs, evidence, and rationale → Chosen option, consequences, and revisit triggers.
- **Key discipline**: Avoid comparing options solely through generic checklists of pros and cons. Anchor trade-offs to the concrete constraints and operational realities of the project.

### 7. Project panorama and design exposition
- **Reader question**: What does this system look like, why was it designed this way, and how do its components operate end-to-end?
- **Suggested flow**:
  1. **Positioning & boundaries**: Why the project exists, target users, problems solved, explicit non-goals, core terminology.
  2. **Current state & baseline**: Exact release or worktree baseline date/commit, implemented versus planned features, known operational limits (separating implementation, verification, and publication status).
  3. **Design principles & trade-offs**: Provenance of constraints, how principles governed design, concrete rejected alternatives, and accepted trade-offs.
  4. **Overall architecture**: Module responsibilities, dependency topology, state and data storage, system interface boundaries. Illustrated with architecture or data flow diagrams accompanied by textual explanation.
  5. **Concrete feature flows**: End-to-end traversal from user trigger to output. Input/output contracts, step-by-step execution, inter-module invocations, branching, failure recovery, side effects, and exact code anchor paths.
  6. **Validation & limitations**: Empirical checks supporting claims, untested boundaries, and impact of known defects on usage.
  7. **Version evolution & trajectory**: Milestones explaining *why* designs evolved, behavioral changes, backward compatibility, migration impacts, superseded architectures, and future roadmap.
- **Key discipline**: Organize across three distinct depths: Overview (broad system landscape), Monographs (deep dives into critical subsystems/features), and Evidence Anchors (pointers to code, tests, design records, and commit history). Never replace explanations with a bare list of file paths. Connect every key feature across: `User Scenario → External Behavior → Internal Flow & Modules → Design Rationale → Verification Evidence`.

## Local modular content and composition

Enhance primary articles by embedding targeted content blocks where helpful, without
forcing these names as rigid heading titles:

| Modular Content | Purpose & Preservation Guidance |
| --- | --- |
| Prerequisites, materials & time checklist | Upfront preparation for procedures; preserve validity duration, dependencies, and branch conditions. |
| Minimal runnable example & exercise | Grounding abstract concepts or skills; preserve environment requirements, input, expected output, and key explanation. |
| Worked problem analysis & self-test | Evaluating concept application; clearly explain conditions, reasoning, and why plausible distractors fail. |
| Syllabus mapping & confusion matrix | Exam and certification prep; distinguish explicit exam rules, sample questions, and personal deductions. |
| Derivation or experimental record | Validating hypotheses; preserve hypotheses, setup, empirical data, counterexamples, and incomplete gaps. |
| Diagnostic attempt log | Troubleshooting reuse; preserve the timeline of hypotheses, changes, observations, and changing conclusions. |

### Composition and splitting guidelines

- **Keep together**: When auxiliary modules directly serve the reader's immediate single task (such as presenting a minimal framework task, explaining its runtime mechanism, diagnosing two common pitfalls, and verifying the result), keep them in one coherent article.
- **Split apart**: Split into separate documents when reader goals fundamentally conflict (e.g., certification exam prep versus open-ended academic research), when background prerequisites diverge significantly, or when a feature monograph requires independent lifecycle maintenance.
- **Avoid empty headings**: A concise entry should explain its topic directly without adding empty placeholder headings merely to satisfy a template.

## Human reading organization

- Write in the user's language using the field's ordinary terms. English Skill
  instructions and examples do not require English knowledge entries. Preserve
  precise symbols and API names, explaining unfamiliar terms before using them.
- Lead with a concise summary stating what question the entry answers, the primary takeaway, or the current state.
- Tailor reading sequence to the reader's background:
  - Deductive sequence (`Problem → Definition → Derivation → Concrete calculation`) serves readers with mathematical or theoretical foundations.
  - Inductive sequence (`Observed phenomenon → Minimal runnable example → Internal mechanism → Boundary variations`) serves readers learning practical engineering skills.
- Maintain coherent narrative flow without forcing mathematical definitions, multi-step derivations, or multi-dimensional comparisons into wall-of-text paragraphs:
  - Keep short symbols, local conditions, and non-disruptive relationships in inline math (`$...$`).
  - Present core objects, key equalities/inequalities, long expressions, and compared relations as standalone display formulas (`$$...$$`), with variable explanations, preconditions, and conclusions immediately adjacent.
  - Use multi-line environments such as `aligned` for multi-step derivations rather than overlong single lines.
  - Use tables when comparing multiple models, dimensions, parameters, or outcomes.
  - Use numbered steps for derivations, algorithms, or operational procedures with logical dependencies, not solely strict chronological time sequences.
  - Keep sentences and explanatory prose outside math delimiters; never wrap full explanations inside `\text{...}` to bypass delimiter rules.
- Place raw telemetry logs, extensive commit histories, and exhaustive source lists at the bottom of the article or in working records.

An overview explains the whole project; a feature page develops the necessary
detail. There is no fixed limit of one or two feature flows. Include the branches,
state changes, and implementation details needed for the agreed questions, with
versioned evidence pointers rather than a file-by-file source-code paraphrase.
Label a knowledge-base project account with its source baseline and review date;
it is not an automatically synchronized substitute for the project's current
status authority. Maintain affected explanations and meaningful evolution notes,
without duplicating entire old articles after every change.

## Placement of conditions and grounding boundaries

- Place every condition that alters a conclusion, calculation, or step immediately adjacent to that conclusion, calculation, or step.
- Ground all factual assertions, parameters, hardware specifics, APIs, and procedural steps strictly in authorized source materials. Never synthesize ungrounded specifics from parametric memory.
- If relevant supplementary context from within the knowledge base is incorporated, explicitly label its provenance (e.g., `> Supplementary source: [entry name]`).
- If an essential answer is unavailable in authorized materials, explicitly state the gap and its impact; never fill gaps with plausible guesses.

## Content acceptance

Reviewers (and authors self-checking drafts) must inspect the actual prose and compare it against the source material:

1. **Reader problem**: Does the article directly answer the agreed questions, and is the core conclusion readily discoverable?
2. **Explanatory completeness**: Are the reasoning, mechanisms, concrete numbers, units, and conditions sufficiently explained without forcing the reader to reopen raw sources for core answers?
3. **Epistemic integrity**: Are facts, author claims, personal inferences, and conjectures clearly distinguishable? Are open questions and unproved gaps honestly disclosed?
4. **Strict grounding**: Is every factual claim, parameter, and procedure grounded in authorized sources or labeled supplementary references, with zero ungrounded hallucinations?
5. **Operational validity**: Can a reader execute the steps, replicate the calculation, or diagnose the problem based on the text? Are error paths and failure recoveries documented?

Use specific passages and omissions, not length, heading counts, or a completed
checklist, to support the result. Structural validation does not establish content
quality. For workflows using `PASS / FIX / BLOCKED`, missing available answers,
incorrect examples, and labels in place of explanations are `FIX`; missing
evidence or decisions necessary for the agreed deliverable are `BLOCKED`. Accept
a supported partial result only with its narrower scope explicit, without silently
reducing a user-required complete result. A short completion message does not
impose a short stored article.

For detailed reference examples demonstrating these patterns across all seven starting points and multi-depth project documentation, consult [knowledge-writing-examples.md](knowledge-writing-examples.md) and the dedicated case studies under [writing-examples/](writing-examples/).
