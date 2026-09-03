---
name: resume-edit
description: Generate a validated preview candidate for authorized ResumeBranch resume-content or supported layout edits. Use after the requested target and result are clear; do not use for read-only advice, visual inspection, or unconfirmed facts.
metadata:
  version: "1.0.0"
  compatibility: ResumeBranch backend with Python 3.11+ and project dependencies.
  entrypoint: scripts/run.py:run
  tool-name: resume_edit
  tool-input-schema: references/tool-input.schema.json
  runtime-context-schema: references/runtime-context.schema.json
  output-schema: references/output.schema.json
---

# Resume Edit

Generate a deterministic candidate for the existing preview-and-confirmation flow. This Skill never saves the resume.

## Use this Skill

- Use it when the user has explicitly authorized a concrete resume-content change or a supported conversational layout change.
- If a target, referenced suggestion, fact, or intended result is unclear, ask one focused clarification question first.
- Do not use it for analysis-only requests, ordinary questions, font-family changes, font-size changes handled by dedicated UI controls, CSS, coordinates, or arbitrary new fields.

## Invocation

The model supplies only the fields defined in [the Tool input schema](references/tool-input.schema.json). Current resume data, layout, task context, and base revision are trusted runtime inputs defined in [the runtime context schema](references/runtime-context.schema.json); never reconstruct or submit them as Tool arguments.

For each operation:

- Use only `set`, `replace`, `append`, `insert`, `remove`, or `move`.
- Use paths and value shapes from the ResumeBranch resume/layout contract already present in the active system context.
- Include `expected` when changing or removing an existing value if the current value is known.
- Supply only operations explicitly authorized in this request. Never submit the complete resume or layout object.
- Put independent answers or necessary clarification alongside otherwise executable edits in `answer_text`; leave it empty for a pure edit request.

The entrypoint validates operation count, path scope, semantic targets, value shapes, layout capabilities, and base revision. Its output follows [the output schema](references/output.schema.json) and must be handed to the existing confirmation flow. Do not claim that a candidate has been saved or applied.
