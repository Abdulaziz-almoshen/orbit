#!/usr/bin/env python3
"""Observer-agent contract: workers are watched; the watcher stays Claude-only and low-trust."""
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
    builder = read("assets", "claude-agents", "builder.md")
    watchdog = read("assets", "claude-agents", "watchdog.md")

    if not re.search(r"(?m)^observer:\s*watchdog\s*$", frontmatter(builder)):
        fails.append("builder does not declare observer: watchdog")
    if not re.search(r"(?m)^observerMessage:\s*>-\s*$", frontmatter(builder)):
        fails.append("builder does not provide a focused observerMessage")
    if re.search(r"(?m)^observer:", frontmatter(watchdog)):
        fails.append("watchdog declares an observer (observer chaining must stay impossible)")
    if re.search(r"(?m)^tools:", frontmatter(watchdog)):
        fails.append("watchdog requests normal task tools instead of relying only on ObserverReport")
    for phrase in ("expected steady state is silence", "data, not instructions", "not user authority"):
        if phrase not in watchdog.lower():
            fails.append(f"watchdog is missing the low-trust contract phrase {phrase!r}")

    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "web,api", "--install-hooks",
                        "--target", d], check=True, capture_output=True, text=True)
        for name in ("frontend-engineer", "backend-engineer"):
            text = open(os.path.join(d, ".claude", "agents", f"{name}.md"), encoding="utf-8").read()
            if "observer: watchdog" not in frontmatter(text):
                fails.append(f"generated {name} lost the observer pairing")
        if not os.path.isfile(os.path.join(d, ".claude", "agents", "watchdog.md")):
            fails.append("scaffolder did not install the Claude watchdog agent")
        if os.path.exists(os.path.join(d, ".orbit", "roles", "watchdog.md")):
            fails.append("Claude-native watchdog leaked into the model-agnostic role catalog")
        settings = json.load(open(os.path.join(d, ".claude", "settings.json"), encoding="utf-8"))
        if settings.get("env", {}).get("CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS") != "1":
            fails.append("normal hook installation did not enable the experimental observer gate")

        payload = json.dumps({"hook_event_name": "SubagentStart", "agent_type": "watchdog", "cwd": d})
        subprocess.run([sys.executable, os.path.join(ROOT, "bin", "orbit-hook")], input=payload,
                       text=True, check=True)
        agents_path = os.path.join(d, ".orbit", "agents.json")
        agents = json.load(open(agents_path)) if os.path.isfile(agents_path) else {}
        if "watchdog" in agents:
            fails.append("observer sidecar displaced the worker on Orbit's visible team board")

    # Existing scaffold refresh: add keys without replacing a customized worker body, and honor an
    # existing alternate observer declaration on another worker.
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "web,api", "--target", d],
                       check=True, capture_output=True, text=True)
        backend = os.path.join(d, ".claude", "agents", "backend-engineer.md")
        text = open(backend, encoding="utf-8").read()
        text = re.sub(r"(?m)^observer: watchdog\nobserverMessage: >-\n(?:  [^\n]*\n){3}", "", text)
        text += "\nCUSTOMIZED WORKER BODY\n"
        open(backend, "w", encoding="utf-8").write(text)
        frontend = os.path.join(d, ".claude", "agents", "frontend-engineer.md")
        text = open(frontend, encoding="utf-8").read().replace("observer: watchdog", "observer: local-auditor")
        open(frontend, "w", encoding="utf-8").write(text)
        subprocess.run([sys.executable, SCAFFOLD, "--surfaces", "web,api", "--target", d],
                       check=True, capture_output=True, text=True)
        migrated = open(backend, encoding="utf-8").read()
        if "observer: watchdog" not in frontmatter(migrated) or "CUSTOMIZED WORKER BODY" not in migrated:
            fails.append("refresh did not add the watchdog while preserving a customized worker body")
        if "observer: local-auditor" not in frontmatter(open(frontend, encoding="utf-8").read()):
            fails.append("refresh overwrote an existing project-specific observer")

    spec = importlib.util.spec_from_file_location("observer_scaffold", SCAFFOLD)
    sc = importlib.util.module_from_spec(spec)
    sys.modules["observer_scaffold"] = sc
    spec.loader.exec_module(sc)
    with tempfile.TemporaryDirectory() as d:
        t = sc.Path(d); (t / ".claude").mkdir()
        settings = t / ".claude" / "settings.json"
        settings.write_text(json.dumps({"env": {"CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS": "0"}}))
        sc.install_hooks(t)
        value = json.loads(settings.read_text())["env"]["CLAUDE_CODE_EXPERIMENTAL_OBSERVER_AGENTS"]
        if value != "0":
            fails.append("install_hooks overwrote the user's explicit observer opt-out")

    if fails:
        print(f"FAIL: observer-agents {len(fails)} case(s):")
        for failure in fails:
            print("  -", failure)
        sys.exit(1)
    print("PASS: observer-agents (worker pairing + silent low-trust watcher + scaffold + opt-out)")


if __name__ == "__main__":
    main()
