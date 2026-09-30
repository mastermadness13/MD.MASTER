---
description: Refine a rough or underspecified prompt into a self-contained, executable prompt, with a change log, assumption ledger, and risk list.
agent: refine-prompt
---

Read `.opencode/agent/refine-prompt.md` and execute the pipeline defined there in full.

`original_prompt` is the text below. If it is empty, the MISSING-INPUT RULE in that
file applies: do not invent a prompt, emit the INPUT REQUIRED block, and stop.

If the text below contains `key: value` lines matching any of the file's inputs
(feedback, iterations, mode, use_case, context), treat them as those inputs.
Everything else is `original_prompt` verbatim.

ORIGINAL PROMPT
$ARGUMENTS
