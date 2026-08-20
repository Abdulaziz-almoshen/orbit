# Repository intelligence — understand the goal without reading the repository

Orbit must understand the product impact of a request, but no role is allowed to ingest the raw
repository. Repository intelligence separates **repository-wide computation** from **model context**.

## Binding sequence

1. `scripts/orbit-intel update` walks eligible file metadata. It reads and re-extracts only new or
   size/mtime-changed files, verifies them by SHA-256, and removes deleted files.
2. Deterministic extractors record file topology, manifests/build targets, symbols, imports, API
   routes, event producers/consumers, SQL tables, config, tests, CODEOWNERS, and bounded Git
   co-change history in `.orbit/intelligence/index.sqlite3`.
3. Task intake converts the user's goal to lexical terms, ranks matching facts, and expands one
   relationship hop. The result is `.orbit/intelligence/latest.json`.
4. Roles receive a view of that packet, never the database and never a repository dump. Every fact
   carries a path, line, extractor, and confidence.

## Product-manager meaning

| Indexed signal | Product question it answers |
|---|---|
| Directory/package topology | Which product, application, or service owns this experience? |
| Build targets/manifests | What independently deployable or testable units may change? |
| Symbols, definitions, imports | Where does the behavior live and what code depends on it? |
| API routes and consumers | Which customer/system journeys cross this contract? |
| Events and subscribers | What asynchronous behavior can break outside the immediate screen? |
| Database schemas/migrations | What durable data and compatibility obligations are involved? |
| Configuration ownership | Which environment, flag, or operational setting controls behavior? |
| Tests and production affinity | What existing proof should be run or extended? |
| CODEOWNERS/service ownership | Who is accountable for review or operational approval? |
| Git co-change edges | Which files historically move together even when static imports miss them? |

## Hard limits and uncertainty

- Default maximum: 12 files, one hop, approximately 4,000 evidence tokens.
- The indexer makes zero model calls and uses no network.
- A regex-derived fact is labeled lower confidence than a language AST fact; it is never presented
  as certainty.
- Empty or weak retrieval is a visible coverage warning, not permission to guess.
- Expansion is targeted: name the missing question, issue another query, and add only the smallest
  evidence slice. Do not recursively widen to the entire repository.
- AgentPrune governs communication between roles; repository retrieval governs evidence entering
  that graph. Neither may prune the goal, Safety, Reviewer, QA, CPO, or required proof.

## Operator commands

```bash
scripts/orbit-intel update
scripts/orbit-intel query --goal "reschedule an interview without losing panel availability"
scripts/orbit-intel stats
```

The index is derived and disposable. Delete `.orbit/intelligence/index.sqlite3` only when a clean
rebuild is intentionally required; the next update recreates it.
