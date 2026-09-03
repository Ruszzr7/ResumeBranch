---
name: resume-snapshot
description: Render the current ResumeBranch resume through the real PDF pipeline as bounded color PNG page images for visual inspection. Use for pagination, spacing, alignment, overflow, hierarchy, density, or overall page-quality questions; do not use for text-only questions.
metadata:
  version: "1.0.0"
  compatibility: ResumeBranch backend with Python 3.11+, PDF rendering dependencies, and Poppler.
  entrypoint: scripts/run.py:run
  tool-name: resume_snapshot
  tool-input-schema: references/tool-input.schema.json
  runtime-context-schema: references/runtime-context.schema.json
  output-schema: references/output.schema.json
---

# Resume Snapshot

Render an ephemeral visual snapshot of the current resume using the same PDF generator as export. This Skill is read-only and creates no database row, user-visible file, message, or log containing the images.

## Use this Skill

- Use it when answering requires evidence about actual pages, pagination, whitespace, alignment, overflow, visual hierarchy, density, consistency, or overall appearance.
- Do not infer those properties from layout configuration or resume text when a snapshot is required.
- Do not use it for content-only questions.
- Do not invoke it again after the current turn already has a snapshot.

## Invocation

The model may supply only the optional reason defined in [the Tool input schema](references/tool-input.schema.json). Resume data, layout configuration, photo, temporary browser render style, and rendering limits are trusted inputs supplied by the graph according to [the runtime context schema](references/runtime-context.schema.json).

The entrypoint preserves the existing limits: no more than two pages, 96 DPI by default, bounded image edge length, and bounded total PNG bytes. It returns ephemeral multimodal image parts plus non-sensitive diagnostics described by [the output schema](references/output.schema.json). Treat the images as evidence about the current rendering, not as new resume facts.
