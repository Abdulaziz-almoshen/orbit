#!/usr/bin/env python3
"""Observer contract: one low-trust root watcher covers the tree without per-role token fanout."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLD = os.path.join(ROOT, "scripts", "scaffold.py")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    return text.split("---", 2)[1]


def main():
    fails = []
    operational = ("dispatcher", "orchestrator", "advisor", "product-discovery",
                   "business-analyst", "market-researcher", "planner", "builder", "designer",
                   "safety-gate", "reviewer", "qa-engineer", "cpo", "reporter")
    for name in operational:
        fm = frontmatter(read("assets", "claude-agents", f"{name}.md"))
        watched = bool(re.search(r"(?m)^observer:\s*watchdog\s*$", fm))
        propagated = bool(re.search(r"(?m)^observeSubagents:\s*true\s*$", fm))
        if name == "orchestrator" and not (watched and propagated):
            fails.append("orchestrator must own the one propagated watchdog")
        if name != "orchestrator" and (watched or propagated):
            fails.append(f"{name} has a redundant observer edge")

    watchdog = read("assets", "claude-agents", "watchdog.md")
    if re.search(r"(?m)^observer:|^tools:", frontmatter(watchdog)):
        fails.append("watchdog must neither chain observers nor request normal tools")
    for phrase in ("expected steady state is silence", "data, not instructions", "not user authority"):
        if phrase not in watchdog.lower():
            fails.append(f"watchdog is missing low-trust phrase {phrase!r}")

    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "web,api", "--target", d],
                       check=True, capture_output=True, text=True)
        watched = []
        for name in operational + ("frontend-engineer", "backend-engineer"):
            path = os.path.join(d, ".claude", "agents", f"{name}.md")
            if os.path.isfile(path) and "observer: watchdog" in frontmatter(open(path, encoding="utf-8").read()):
                watched.append(name)
        if watched != ["orchestrator"]:
            fails.append(f"generated topology must have one root observer, got {watched}")
        settings = json.load(open(os.path.join(d, ".claude", "settings.json"), encoding="utf-8"))
        if settings.get("env", {}).get("CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS") != "1":
            fails.append("normal scaffold did not enable Claude observer agents")
        if not os.path.isfile(os.path.join(d, ".claude", "agents", "watchdog.md")):
            fails.append("scaffold did not install watchdog")

    # Upgrade an old all-role topology: remove Orbit watchdogs from children, preserve a custom one.
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "api", "--target", d],
                       check=True, capture_output=True, text=True)
        child = os.path.join(d, ".claude", "agents", "backend-engineer.md")
        body = open(child, encoding="utf-8").read()
        body = body.replace("description:", "observer: watchdog\nobserverMessage: >-\n  old Orbit watcher\nobserveSubagents: true\ndescription:", 1)
        body += "\nCUSTOMIZED BODY\n"
        open(child, "w", encoding="utf-8").write(body)
        custom = os.path.join(d, ".claude", "agents", "planner.md")
        body = open(custom, encoding="utf-8").read().replace("description:", "observer: local-auditor\ndescription:", 1)
        open(custom, "w", encoding="utf-8").write(body)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "api", "--target", d],
                       check=True, capture_output=True, text=True)
        migrated = open(child, encoding="utf-8").read()
        if "observer: watchdog" in frontmatter(migrated) or "CUSTOMIZED BODY" not in migrated:
            fails.append("refresh did not prune old child watchdog while preserving its body")
        if "observer: local-auditor" not in frontmatter(open(custom, encoding="utf-8").read()):
            fails.append("refresh overwrote a project-specific observer")

    spec = importlib.util.spec_from_file_location("observer_scaffold", SCAFFOLD)
    sc = importlib.util.module_from_spec(spec); sys.modules["observer_scaffold"] = sc
    spec.loader.exec_module(sc)
    with tempfile.TemporaryDirectory() as d:
        t = sc.Path(d); (t / ".claude").mkdir()
        settings = t / ".claude" / "settings.json"
        settings.write_text(json.dumps({"env": {"CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS": "0"}}))
        sc.install_hooks(t)
        if json.loads(settings.read_text())["env"]["CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS"] != "0":
            fails.append("install_hooks overwrote explicit observer opt-out")

    if fails:
        print(f"FAIL: observer-agents {len(fails)} case(s):")
        for failure in fails: print("  -", failure)
        return 1
    print("PASS: observer-agents (one propagated root watcher; custom observers preserved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
