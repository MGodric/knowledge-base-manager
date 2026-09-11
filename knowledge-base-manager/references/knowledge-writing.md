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

## Organize complete explanations

Use familiar topic names and the terminology readers of the field actually use.
Prefer a concrete title such as “申请材料与办理顺序” when that is the content.
Abstract labels are appropriate when they name a real concept that the article
explains, not merely when they make a heading sound formal.

Lead with the answer, main idea, or useful action, then give the reasoning and
details needed to understand it. Connect conclusions to their causes, examples,
and conditions. Keep related material together; do not split a concept, its
assumptions, and its worked example solely to produce more entries.

Choose the structure by purpose, not by a universal template:

- For a procedure, explain applicable conditions, inputs or materials, sequence,
  timing/dependencies, meaningful branches, and failure handling where supported.
- For explanatory or research knowledge, explain the question, concepts,
  mechanism or derivation, a useful example, and what the result establishes.
  Preserve equations, units, and project evidence that matter to understanding.
- For a decision, explain the available options, selection criteria, tradeoffs,
  and when the decision should be revisited.
- For a source or project page, help readers find and understand the substantive
  knowledge; avoid replacing it with a catalog of what was processed.

These are prompts for relevance, not required chapters. An administrative
example does not make every topic an application guide; a research entry need
not be converted into an SOP.

Keep concrete details that change the answer: numbers and their units, time
windows, prerequisites, equality cases, inputs/outputs, and exceptional paths.
Use examples to make a mechanism or choice understandable. An illustrative
example must be identified as such and be consistent with the supported model;
it must not invent regulations, measured results, or source claims.

## Write naturally without flattening the subject

Use the user's language and the field's ordinary terms. Preserve standard
English terms, API names, symbols, and evidence labels where they carry meaning.
Explain unfamiliar terms before building an argument on them. An English source
does not require carrying ordinary English nouns into Chinese prose: use
established Chinese terminology naturally, optionally giving the English term
on first use. Keep APIs, symbols, proper names, and evidence labels accurate.

Prefer a subject and a concrete verb over chains of abstract nouns. Explain
what happens, why it happens, and what follows. A table can compare repeated
dimensions; it should not reduce a mechanism to a list of labels. Keep prose
where it supplies the reasoning that a table or checklist cannot.

Remove repetitive introductions, meta-commentary about the act of synthesis,
and unsupported rhetorical contrasts. Do not use a banned-word list, sentence
quota, minimum word count, or disclaimer ratio. Concision removes redundancy;
it does not remove the explanation the reader needs. Likewise, length alone
does not establish usefulness.

For complete Chinese examples of weak and improved articles, read
[knowledge-writing-examples.md](knowledge-writing-examples.md) when calibrating
a draft or resolving a writing-quality failure. The examples illustrate choices,
not wording to copy into unrelated entries.

## Put conditions where they change the answer

A condition that changes a calculation, conclusion, or action belongs beside
that calculation, conclusion, or action. Keep it visible. A common scope or
version can be stated once near the beginning. Do not repeat it after every
paragraph unless the distinction changes.

Keep review history, access checks, coverage accounting, and audit status in
the sources area or working record, as appropriate. Formal entries still need
their own supporting provenance and essential conditions; a separate record
never substitutes for these.

Preserve scientific assumptions, proof conditions, experiment limits, and
meaningful distinctions between sourced facts and inference. When relevant,
state the precise limitation once with its practical or explanatory consequence.
Avoid chains of “this only shows X, not Y or Z” where Y and Z are unrelated to
the reader's actual question. Do not remove a necessary qualification merely
to make the prose sound confident.

If sources establish a rule, describe the rule and how to use it. “Check the
official website” is a source/version reminder, not a replacement for the
requirements already available. If an important answer is missing, identify
that answer and its effect on the intended use.

## Content acceptance

Read the actual article, not only the editor's manifest. For each important
question, locate the answer and judge whether its explanation, example, or steps
are sufficient for the agreed reader. Check:

- Can the reader answer the question or perform the agreed preparation from the
  body? Is the main answer easy to find?
- Are the reasons and concrete details preserved well enough to understand why,
  how, and when the answer applies?
- Must the reader reopen the original source to verify a current version or
  inspect further detail, or because the article omitted the main answer?
- Do qualifications change a relevant decision or understanding, or repeat
  process reminders that obscure the content?
- Are there factual errors, unsupported inferences, or sensitive details that
  should not have been retained?
- Are all factual claims, parameters, and procedures strictly grounded in the
  authorized source materials or explicitly labeled internal references
  (`> 补充来源: ...`), with zero ungrounded parametric extrapolation or
  hallucinated details?

Use specific passages and omissions when reporting the result; do not score by
length, entry count, keywords, or formatting. A clean structural audit and a
completed ledger cannot answer these questions.

For workflows using `PASS / FIX / BLOCKED`, apply them to the agreed deliverable:
`FIX` includes available core answers omitted from the body, labels in place of
explanations, or incorrect steps/examples. `BLOCKED` identifies an actual missing
decision or evidence required to complete that deliverable. A supported partial
result can be accepted within a clearly stated narrower coverage; the unresolved
question remains visible and must not be counted as answered. Do not silently
reduce a user-required complete result to a partial one.

The completion report may be short. Its length preference does not limit the
stored body unless the user explicitly requested a short entry.
