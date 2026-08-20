#!/usr/bin/env python3
"""Orbit repository intelligence: deterministic index + bounded task retrieval.

No model and no network are used. The repository is scanned once, then refreshed by content hash.
Every returned claim retains file/line/extractor provenance. Retrieval starts with lexical and symbol
matches and expands at most one graph hop by default; the output is capped before it reaches an agent.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA = 2
SOURCE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".kt", ".kts",
    ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".scala", ".sql", ".graphql", ".proto",
    ".sh", ".bash", ".zsh", ".yaml", ".yml", ".json", ".toml", ".xml", ".gradle",
}
MANIFESTS = {
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "pom.xml",
    "build.gradle", "build.gradle.kts", "settings.gradle", "Makefile", "Dockerfile",
    "docker-compose.yml", "docker-compose.yaml", "workspace.json", "nx.json", "turbo.json",
}
IGNORED_DIRS = {
    ".git", ".orbit", ".claude", ".idea", ".vscode", "node_modules", "vendor", "dist", "build", "target",
    "coverage", ".next", ".nuxt", ".venv", "venv", "__pycache__", ".cache", ".tox",
}
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,63}")
GENERIC_SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:class|interface|enum|type|function|def|fn|struct|trait)\s+"
    r"([A-Za-z_$][\w$]*)", re.MULTILINE)
IMPORT_PATTERNS = [
    re.compile(r"(?:from|import)\s+['\"]([^'\"]+)['\"]"),
    re.compile(r"(?:require\s*\(|from\s+)(?:['\"])([^'\"]+)") ,
    re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE),
]
ROUTE_PATTERNS = [
    re.compile(r"(?:app|router|route)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)", re.I),
    re.compile(r"@(Get|Post|Put|Patch|Delete)Mapping\s*\(\s*['\"]?([^'\")]+)", re.I),
    re.compile(r"@(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)", re.I),
]
EVENT_PATTERNS = [
    re.compile(r"(?:emit|publish|dispatch|produce)\s*\(\s*['\"]([^'\"]+)['\"]", re.I),
    re.compile(r"(?:on|subscribe|consume|listen)\s*\(\s*['\"]([^'\"]+)['\"]", re.I),
]
CONFIG_NAMES = re.compile(r"(?:config|settings|\.env|application\.(?:yml|yaml|properties))", re.I)
TEST_NAMES = re.compile(r"(?:^|/)(?:tests?|specs?)/|(?:test_|_test\.|\.test\.|\.spec\.)", re.I)
GENERIC_CALL = re.compile(r"\b([A-Za-z_$][\w$]{2,})\s*\(")
CALL_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "function", "def", "class", "super"}
STOPWORDS = {"the", "and", "for", "with", "from", "this", "that", "into", "when", "what", "then",
             "user", "want", "make", "should", "code", "file", "project", "orbit", "implement"}


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL, lines INTEGER NOT NULL, kind TEXT NOT NULL, updated_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS facts(id INTEGER PRIMARY KEY, path TEXT NOT NULL, line INTEGER NOT NULL,
        kind TEXT NOT NULL, name TEXT NOT NULL, detail TEXT NOT NULL, extractor TEXT NOT NULL,
        confidence REAL NOT NULL, UNIQUE(path,line,kind,name,detail));
      CREATE TABLE IF NOT EXISTS edges(src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL,
        weight REAL NOT NULL, evidence TEXT NOT NULL, PRIMARY KEY(src,dst,kind));
      CREATE TABLE IF NOT EXISTS terms(term TEXT NOT NULL, path TEXT NOT NULL, fact_id INTEGER NOT NULL,
        PRIMARY KEY(term,fact_id));
      CREATE INDEX IF NOT EXISTS facts_path ON facts(path);
      CREATE INDEX IF NOT EXISTS facts_name ON facts(name);
      CREATE INDEX IF NOT EXISTS edges_src ON edges(src);
      CREATE INDEX IF NOT EXISTS edges_dst ON edges(dst);
      CREATE INDEX IF NOT EXISTS terms_term ON terms(term);
      CREATE INDEX IF NOT EXISTS terms_path ON terms(path);
    """)
    columns = {row[1] for row in con.execute("PRAGMA table_info(files)")}
    if "mtime_ns" not in columns:
        con.execute("ALTER TABLE files ADD COLUMN mtime_ns INTEGER NOT NULL DEFAULT 0")
    existing = con.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
    if existing and existing[0] != str(SCHEMA):
        con.executescript("DELETE FROM terms; DELETE FROM edges; DELETE FROM facts; DELETE FROM files; DELETE FROM meta;")
    con.execute("INSERT OR IGNORE INTO meta VALUES('schema', ?)", (str(SCHEMA),))
    return con


def _kind(path: str) -> str:
    name = Path(path).name
    if name in MANIFESTS:
        return "manifest"
    if name.upper() == "CODEOWNERS":
        return "ownership"
    if TEST_NAMES.search(path):
        return "test"
    if Path(path).suffix.lower() == ".sql":
        return "schema"
    if CONFIG_NAMES.search(path):
        return "config"
    return "source"


def _iter_files(root: Path, max_file_bytes: int):
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".orbit"))
        for name in sorted(files):
            p = Path(base) / name
            rel = p.relative_to(root).as_posix()
            if name not in MANIFESTS and name.upper() != "CODEOWNERS" and p.suffix.lower() not in SOURCE_EXTS:
                continue
            try:
                stat = p.stat()
                if p.is_symlink() or stat.st_size > max_file_bytes:
                    continue
                yield rel, p, stat
            except OSError:
                continue


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _add_fact(out: list, path: str, line: int, kind: str, name: str, detail: str,
              extractor: str, confidence: float = 0.8):
    out.append((path, max(1, line), kind, name[:180], detail[:500], extractor, confidence))


def _extract(path: str, raw: bytes) -> tuple[list, list]:
    text = raw.decode("utf-8", "replace")
    facts, imports = [], []
    k = _kind(path)
    _add_fact(facts, path, 1, "file", Path(path).name, k, "filesystem", 1.0)
    parent = Path(path).parent.as_posix()
    if parent != ".":
        _add_fact(facts, path, 1, "topology", parent, Path(path).name, "filesystem", 1.0)
    if k == "manifest":
        _add_fact(facts, path, 1, "build_target", Path(path).parent.as_posix(), Path(path).name,
                  "manifest", 0.95)
    if k == "config":
        _add_fact(facts, path, 1, "config_owner", Path(path).stem, path, "filename", 0.75)
    if k == "test":
        _add_fact(facts, path, 1, "test", Path(path).stem, path, "test-path", 0.95)
    if Path(path).name.upper() == "CODEOWNERS":
        for no, row in enumerate(text.splitlines(), 1):
            row = row.strip()
            if row and not row.startswith("#") and len(row.split()) >= 2:
                pattern, *owners = row.split()
                _add_fact(facts, path, no, "owner", pattern, " ".join(owners), "CODEOWNERS", 1.0)

    if Path(path).suffix.lower() in {".py", ".pyi"}:
        try:
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    _add_fact(facts, path, node.lineno, "symbol", node.name, type(node).__name__, "python-ast", 1.0)
                elif isinstance(node, ast.Import):
                    imports.extend((a.name, node.lineno) for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append((node.module, node.lineno))
                elif isinstance(node, ast.Call):
                    target = node.func.id if isinstance(node.func, ast.Name) else (
                        node.func.attr if isinstance(node.func, ast.Attribute) else "")
                    if target:
                        _add_fact(facts, path, node.lineno, "call", target, "call expression", "python-ast", 1.0)
        except (SyntaxError, ValueError):
            pass
    else:
        for m in GENERIC_SYMBOL.finditer(text):
            _add_fact(facts, path, _line(text, m.start()), "symbol", m.group(1), "declaration",
                      "conservative-regex", 0.7)
        for pat in IMPORT_PATTERNS:
            for m in pat.finditer(text):
                name = next((g for g in m.groups() if g), "")
                if name:
                    imports.append((name, _line(text, m.start())))
        for m in GENERIC_CALL.finditer(text):
            if m.group(1).lower() not in CALL_KEYWORDS:
                _add_fact(facts, path, _line(text, m.start()), "call", m.group(1), "possible call",
                          "conservative-regex", 0.55)
    for name, no in imports:
        _add_fact(facts, path, no, "import", name, name, "language-import", 0.85)
    for pat in ROUTE_PATTERNS:
        for m in pat.finditer(text):
            method, route = m.group(1).upper(), m.group(2)
            _add_fact(facts, path, _line(text, m.start()), "api_route", f"{method} {route}", route,
                      "route-pattern", 0.85)
    for pat in EVENT_PATTERNS:
        for m in pat.finditer(text):
            verb = text[m.start():m.start()+24].split("(", 1)[0].strip()
            kind = "event_producer" if re.search(r"emit|publish|dispatch|produce", verb, re.I) else "event_consumer"
            _add_fact(facts, path, _line(text, m.start()), kind, m.group(1), verb, "event-pattern", 0.8)
    if Path(path).suffix.lower() == ".sql":
        for m in re.finditer(r"\b(?:CREATE|ALTER)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([\w.]+)", text, re.I):
            _add_fact(facts, path, _line(text, m.start()), "database_schema", m.group(1), m.group(0),
                      "sql-parser", 0.95)
    return facts, imports


def _resolve_import(src: str, name: str, all_paths: set[str]) -> str | None:
    stem = name.replace(".", "/").lstrip("./")
    src_dir = Path(src).parent.as_posix()
    candidates = [stem, f"{src_dir}/{stem}" if src_dir != "." else stem]
    for candidate in candidates:
        for ext in SOURCE_EXTS:
            for p in (candidate + ext, candidate + "/index" + ext, candidate + "/__init__.py"):
                if p in all_paths:
                    return p
    suffix = "/" + stem.split("/")[-1]
    hits = sorted(p for p in all_paths if Path(p).with_suffix("").as_posix().endswith(suffix))
    return hits[0] if len(hits) == 1 else None


def _git_cochange(root: Path, limit: int = 200) -> Counter:
    pairs = Counter()
    try:
        out = subprocess.run(["git", "log", f"-{limit}", "--name-only", "--pretty=format:@@"],
                             cwd=root, text=True, capture_output=True, timeout=20, check=False).stdout
        for block in out.split("@@"):
            paths = sorted({x.strip() for x in block.splitlines() if x.strip() and not x.startswith(".orbit/")})
            if len(paths) > 40:
                continue
            for i, a in enumerate(paths):
                for b in paths[i+1:]:
                    pairs[(a, b)] += 1
    except Exception:
        pass
    return pairs


def _git_head(root: Path) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True,
                              timeout=5, check=False).stdout.strip()
    except Exception:
        return ""


def build(root: Path, max_file_bytes: int = 2_000_000) -> dict:
    root = root.resolve()
    db = root / ".orbit/intelligence/index.sqlite3"
    con = _connect(db)
    before = {r["path"]: r for r in con.execute("SELECT path,sha256,bytes,mtime_ns FROM files")}
    previous_head_row = con.execute("SELECT value FROM meta WHERE key='git_head'").fetchone()
    previous_head = previous_head_row[0] if previous_head_row else None
    git_head = _git_head(root)
    seen, changed, unchanged, metadata_updates, total_bytes = set(), [], 0, 0, 0
    now = int(time.time())
    for path, file_path, stat in _iter_files(root, max_file_bytes):
        seen.add(path); total_bytes += stat.st_size
        prior = before.get(path)
        if prior and prior["bytes"] == stat.st_size and prior["mtime_ns"] == stat.st_mtime_ns:
            unchanged += 1
            continue
        try:
            raw = file_path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:4096]:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if prior and prior["sha256"] == digest:
            con.execute("UPDATE files SET bytes=?,mtime_ns=? WHERE path=?", (len(raw), stat.st_mtime_ns, path))
            metadata_updates += 1
            unchanged += 1
            continue
        facts, imports = _extract(path, raw)
        con.execute("DELETE FROM terms WHERE path=?", (path,))
        con.execute("DELETE FROM facts WHERE path=?", (path,))
        con.execute("DELETE FROM edges WHERE src=? OR dst=?", (path, path))
        con.executemany("INSERT OR IGNORE INTO facts(path,line,kind,name,detail,extractor,confidence) VALUES(?,?,?,?,?,?,?)", facts)
        term_rows = []
        for fact in con.execute("SELECT id,path,kind,name,detail FROM facts WHERE path=?", (path,)):
            searchable = f"{fact['name']} {fact['detail']}"
            if fact["kind"] in ("file", "topology"):
                searchable += " " + path
            term_rows.extend((term, path, fact["id"]) for term in _token_forms(
                searchable))
        con.executemany("INSERT OR IGNORE INTO terms VALUES(?,?,?)", term_rows)
        con.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?)",
                    (path, digest, len(raw), stat.st_mtime_ns, raw.count(b"\n") + 1, _kind(path), now))
        changed.append(path)
    removed = sorted(set(before) - seen)
    if not changed and not removed and previous_head == git_head:
        counts = dict(con.execute("SELECT 'files',count(*) FROM files UNION ALL SELECT 'facts',count(*) FROM facts UNION ALL SELECT 'edges',count(*) FROM edges").fetchall())
        (con.commit() if metadata_updates else con.rollback()); con.close()
        return {"schema": SCHEMA, "changed": 0, "unchanged": unchanged, "removed": 0,
                "changed_paths": [], "source_bytes": total_bytes, **counts}
    for path in removed:
        con.execute("DELETE FROM terms WHERE path=?", (path,))
        con.execute("DELETE FROM facts WHERE path=?", (path,))
        con.execute("DELETE FROM edges WHERE src=? OR dst=?", (path, path))
        con.execute("DELETE FROM files WHERE path=?", (path,))
    all_paths = seen
    # Rebuild cheap derived edges so resolution remains correct after renames/removals.
    con.execute("DELETE FROM edges WHERE kind IN ('import','call','test_of','event','ownership','cochange')")
    for row in con.execute("SELECT path,line,name FROM facts WHERE kind='import'"):
        dst = _resolve_import(row["path"], row["name"], all_paths)
        if dst:
            con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)",
                        (row["path"], dst, "import", 1.0, f"{row['path']}:{row['line']}"))
    symbols = defaultdict(list)
    for row in con.execute("SELECT path,name,line FROM facts WHERE kind='symbol'"):
        symbols[row["name"]].append(row)
    for row in con.execute("SELECT path,name,line,confidence FROM facts WHERE kind='call'"):
        targets = [x for x in symbols.get(row["name"], []) if x["path"] != row["path"]]
        if len(targets) == 1:
            con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)",
                        (row["path"], targets[0]["path"], "call", float(row["confidence"]),
                         f"{row['path']}:{row['line']} calls {row['name']}"))
    sources = [p for p in all_paths if not TEST_NAMES.search(p)]
    for test in (p for p in all_paths if TEST_NAMES.search(p)):
        words = _token_forms(Path(test).stem) - {"test", "spec"}
        ranked = [(len(words & _token_forms(Path(p).stem)), p) for p in sources]
        if ranked and max(ranked)[0] > 0:
            _, target = max(ranked)
            con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)",
                        (test, target, "test_of", 0.8, "filename affinity"))
    events = defaultdict(lambda: {"event_producer": [], "event_consumer": []})
    for row in con.execute("SELECT path,kind,name,line FROM facts WHERE kind LIKE 'event_%'"):
        events[row["name"]][row["kind"]].append(row)
    for name, sides in events.items():
        for a in sides["event_producer"]:
            for b in sides["event_consumer"]:
                con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)",
                            (a["path"], b["path"], "event", 1.0, f"event:{name}"))
    owners = list(con.execute("SELECT name,detail,line FROM facts WHERE kind='owner'"))
    for owner in owners:
        pattern = owner["name"].lstrip("/")
        for path in all_paths:
            directory_rule = pattern.endswith("/") and path.startswith(pattern)
            if not pattern or directory_rule or fnmatch.fnmatch(path, pattern):
                con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)",
                            (path, "owner:" + owner["detail"], "ownership", 1.0,
                             f"CODEOWNERS:{owner['line']}"))
    for (a, b), count in _git_cochange(root).items():
        if a in all_paths and b in all_paths:
            w = min(1.0, 0.2 + count / 10)
            con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)", (a, b, "cochange", w, f"{count} commits"))
            con.execute("INSERT OR REPLACE INTO edges VALUES(?,?,?,?,?)", (b, a, "cochange", w, f"{count} commits"))
    con.execute("INSERT OR REPLACE INTO meta VALUES('root', ?)", (str(root),))
    con.execute("INSERT OR REPLACE INTO meta VALUES('git_head', ?)", (git_head,))
    con.execute("INSERT OR REPLACE INTO meta VALUES('last_build', ?)", (str(now),))
    con.commit()
    counts = dict(con.execute("SELECT 'files',count(*) FROM files UNION ALL SELECT 'facts',count(*) FROM facts UNION ALL SELECT 'edges',count(*) FROM edges").fetchall())
    con.close()
    return {"schema": SCHEMA, "changed": len(changed), "unchanged": unchanged, "removed": len(removed),
            "changed_paths": changed[:20], "source_bytes": total_bytes, **counts}


def _tokens(text: str) -> list[str]:
    # Split camelCase before lexical matching; avoid raw substring matching ("sign" must not match
    # "design"). Prefix affinity is applied separately for plural/long-form identifiers.
    expanded = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    expanded = re.sub(r"[_./:\\-]+", " ", expanded)
    return [w.lower() for w in WORD.findall(expanded) if len(w) > 2 and w.lower() not in STOPWORDS]


def _token_forms(text: str) -> set[str]:
    """Small deterministic morphological expansion for code identifiers; never semantic guessing."""
    forms = set(_tokens(text))
    for word in list(forms):
        if len(word) > 4 and word.endswith("s"):
            forms.add(word[:-1])
        if len(word) > 6 and word.endswith("er"):
            forms.add(word[:-2])
        if len(word) > 7 and word.endswith("ing"):
            forms.add(word[:-3]); forms.add(word[:-3] + "e")
    return forms


def query(root: Path, goal: str, max_tokens: int = 4000, max_files: int = 12, hops: int = 1) -> dict:
    root = root.resolve(); db = root / ".orbit/intelligence/index.sqlite3"
    if not db.exists():
        build(root)
    con = _connect(db)
    terms = sorted(_token_forms(goal))
    scores, reasons, term_scores = defaultdict(float), defaultdict(list), defaultdict(dict)
    if terms:
        placeholders = ",".join("?" for _ in terms)
        rows = con.execute(f"SELECT t.term,f.path,f.kind,f.name,f.detail,f.line,f.extractor,f.confidence "
                           f"FROM terms t JOIN facts f ON f.id=t.fact_id WHERE t.term IN ({placeholders})", terms)
    else:
        rows = []
    for row in rows:
        boost = {"symbol": 3.0, "api_route": 3.0, "event_producer": 2.5, "event_consumer": 2.5,
                 "database_schema": 2.4, "test": 2.0, "owner": 1.3}.get(row["kind"], 1.0)
        value = boost * float(row["confidence"])
        term_scores[row["path"]][row["term"]] = max(value, term_scores[row["path"]].get(row["term"], 0))
        reasons[row["path"]].append({"line": row["line"], "kind": row["kind"], "name": row["name"],
                                     "extractor": row["extractor"], "confidence": row["confidence"]})
    for path, values in term_scores.items():
        scores[path] = sum(values.values())
    seeds = [p for p, _ in sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:max_files]]
    selected = list(seeds)
    if hops > 0:
        for src in list(seeds):
            for e in con.execute("SELECT src,dst,kind,weight,evidence FROM edges WHERE src=? OR dst=? ORDER BY weight DESC", (src, src)):
                other = e["dst"] if e["src"] == src else e["src"]
                if other.startswith("owner:") or other in selected:
                    continue
                if con.execute("SELECT 1 FROM files WHERE path=?", (other,)).fetchone():
                    selected.append(other); scores[other] += e["weight"]
                    reasons[other].append({"line": 1, "kind": "graph:" + e["kind"], "name": src,
                                           "extractor": e["evidence"], "confidence": e["weight"]})
                if len(selected) >= max_files:
                    break
            if len(selected) >= max_files:
                break
    evidence, used = [], 0
    for path in sorted(selected, key=lambda p: (-scores[p], p)):
        item = {"path": path, "score": round(scores[path], 3), "evidence": reasons[path][:5]}
        cost = max(12, len(json.dumps(item, separators=(",", ":"))) // 4)
        if used + cost > max_tokens:
            break
        used += cost; evidence.append(item)
    totals = con.execute("SELECT count(*) files,coalesce(sum(bytes),0) bytes,coalesce(sum(lines),0) lines FROM files").fetchone()
    owners = []
    for item in evidence:
        for e in con.execute("SELECT dst,evidence FROM edges WHERE src=? AND kind='ownership'", (item["path"],)):
            owners.append({"path": item["path"], "owner": e["dst"].removeprefix("owner:"), "evidence": e["evidence"]})
    packet = {
        "schema": 1, "goal": goal[:1000], "policy": {"llm_indexing": False, "hops": min(hops, 1),
        "max_files": max_files, "max_evidence_tokens": max_tokens},
        "repository": {"files": totals["files"], "lines": totals["lines"],
                       "raw_token_estimate": totals["bytes"] // 4},
        "retrieval": {"query_terms": terms[:30], "files": evidence, "owners": owners[:20],
                      "estimated_tokens": used, "coverage_warning": ("no lexical/symbol evidence found" if not evidence else "")},
        "role_views": {
            "product": [x["path"] for x in evidence if any(e["kind"] in {"api_route", "event_producer", "event_consumer", "database_schema"} for e in x["evidence"])],
            "engineering": [x["path"] for x in evidence],
            "qa": [x["path"] for x in evidence if TEST_NAMES.search(x["path"]) or any(e["kind"] == "graph:test_of" for e in x["evidence"])],
            "ownership": owners[:20],
        },
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = root / ".orbit/intelligence/latest.json"; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(packet, indent=2) + "\n")
    con.close()
    return packet


def prepare_goal(root: Path, goal: str, config: dict | None = None) -> dict:
    cfg = (config or {}).get("repository_intelligence") or {}
    if cfg.get("enabled", True) is not True:
        return {}
    started = time.monotonic()
    stats = build(root, int(cfg.get("max_file_bytes", 2_000_000)))
    packet = query(root, goal, int(cfg.get("max_evidence_tokens", 4000)),
                   int(cfg.get("max_files", 12)), min(1, int(cfg.get("default_hops", 1))))
    return {"index": stats, "packet": packet, "elapsed_ms": round((time.monotonic()-started)*1000, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("build", "update", "query", "stats"))
    ap.add_argument("--root", default="."); ap.add_argument("--goal", default="")
    ap.add_argument("--max-tokens", type=int, default=4000); ap.add_argument("--max-files", type=int, default=12)
    args = ap.parse_args(); root = Path(args.root)
    if args.command in ("build", "update"):
        result = build(root)
    elif args.command == "query":
        result = query(root, args.goal, args.max_tokens, args.max_files)
    else:
        con = _connect(root.resolve() / ".orbit/intelligence/index.sqlite3")
        result = dict(con.execute("SELECT 'files',count(*) FROM files UNION ALL SELECT 'facts',count(*) FROM facts UNION ALL SELECT 'edges',count(*) FROM edges").fetchall())
    print(json.dumps(result, indent=2)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
