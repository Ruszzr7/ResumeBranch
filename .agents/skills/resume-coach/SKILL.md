---
name: resume-coach
description: Guide an evidence-driven, multi-turn discussion of a specific resume-content problem. Use when reliable advice requires confirming facts with the user; deep-polish commands activate it explicitly, while other conversations may activate it on demand. Do not use for layout-only analysis, ordinary questions, or an already-clear direct edit.
metadata:
  version: "1.0.0"
  compatibility: ResumeBranch backend with Python 3.11+ and project dependencies.
  entrypoint: scripts/run.py:run
  tool-name: resume_coach
  tool-input-schema: references/tool-input.schema.json
  runtime-context-schema: references/runtime-context.schema.json
  output-schema: references/output.schema.json
---

# Resume Coach

Conduct one evidence-led coaching conversation without changing the resume. The Skill keeps a private, source-traceable record for the current issue and may handle several issues sequentially in one deep-polish session.

## Entering coaching

- A deep-polish command is explicit authorization to start. In the first visible reply, tell the user that the conversation will analyze and collect evidence before any edit, that an edit preview will require a later confirmation, and that they may stop or change topic in natural language at any time.
- In another conversation, if the user explicitly asks for deep questioning or evidence gathering, start and give the same notice.
- If coaching is only your recommendation, explain the change in behavior and ask whether the user wants to enter. Do not call `resume_coach` with `operation=start` until the user agrees.
- Interpret consent and exit requests semantically. Never require a fixed command phrase.

## While active

- Work on one issue at a time. A deep-polish session may move to further issues after the current one is completed or skipped.
- Read the complete current-issue evidence supplied in the active Skill context on every turn.
- Ask at most one focused question per reply. Prefer facts about the situation, goal, personal action, decision, trade-off, and result.
- Use `operation=update` to submit only evidence quoted from the latest user message, plus updated conclusions and unresolved questions.
- You decide semantically whether the evidence is sufficient. Do not use an evidence count, required-question list, or other mechanical threshold.
- Do not fabricate facts or numbers. Do not treat your inference as verified evidence.

## Moving toward an edit

- When evidence is sufficient, first call `resume_coach` with `operation=offer_preview` and a concrete proposed change. Then ask whether the user wants a modification preview generated from that proposal.
- If the user does not approve, continue discussing or collecting evidence. Do not activate the edit Skill.
- Only after the user clearly approves the latest pending offer, call `resume_coach` with `operation=handoff_to_edit`, quoting the approving words from the latest message.
- After a successful handoff, activate `resume-edit` and submit only the authorized operations returned by this Skill. `resume-coach` never creates the edit candidate and never saves the resume.
- The generated candidate still requires the existing preview confirmation before it can be saved.

## Leaving coaching

- When the user clearly asks to stop, pause, skip, return to ordinary chat, or abandon the issue, choose the corresponding `complete_issue` or `exit` operation and acknowledge it naturally.
- An exit keeps the collected record but makes it unavailable to ordinary conversation routing until coaching is activated again.

The Tool input, trusted runtime context, persisted memory, and output contracts are defined in the linked JSON schemas. The entrypoint performs only validation, bounded state updates, authorization binding, and handoff preparation.
