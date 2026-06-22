# BlogForge (WIP)

Internal tool that turns a topic + a few source URLs into a draft blog post. Uses an LLM
to research, outline, and draft. Currently one script we run manually.

## Current pieces
- `pipeline.py` — takes a topic, calls the model to outline then draft, prints markdown.

## Known issues / TODO
- No memory between runs; we keep re-explaining our style guide in the prompt.
- No fact-checking step — the model sometimes invents stats and quotes.
- No structure (research vs. draft vs. edit all in one prompt).
- No limits — a retry loop once ran the model 40 times.
- It can auto-publish to the CMS via `publish()`, which is scary to leave running.
- Env: `MODEL_API_KEY`, `CMS_TOKEN`.
