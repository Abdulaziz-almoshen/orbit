/**
 * Orbit loop on a durable orchestrator — REFERENCE TEMPLATE (Inngest).
 *
 * This maps Orbit's read -> act -> evaluate -> update -> decide loop onto Inngest's durable
 * primitives so it survives restarts: each `step.run()` is a checkpoint (resume skips it,
 * no re-charged model call, no duplicate side effect), `step.invoke()` runs a role as its
 * own retryable sub-function, `retries` + `onFailure` handle failures, and a singleton
 * `concurrency` key stops a scheduled run from stomping a running one.
 *
 * It is a STARTING POINT, not a drop-in: the `callModel` / gate / side-effect bodies are
 * seams you wire to your code. Inngest's SDK API has shifted across versions (e.g. the
 * 2-arg `createFunction(config, trigger, handler)` form below vs. a newer single-config
 * form with `triggers`). Confirm signatures against your installed version:
 * https://www.inngest.com/docs/reference/typescript  — and the working reference,
 * Inngest's own agent harness: https://github.com/inngest/utah
 *
 * Run locally:  npx inngest-cli@latest dev   (then serve/connect this app per the docs).
 */
import { Inngest } from "inngest";

export const inngest = new Inngest({ id: "orbit-loop" });

// --- Layer 1: the loop -------------------------------------------------------------------
// A trigger (cron here; swap for `{ event: "orbit/loop.tick" }`) + a decision in the middle.
export const orbitLoop = inngest.createFunction(
  {
    id: "orbit-loop",
    retries: 3,
    // Singleton per run-key: at most one loop per <unit of work> at a time (no races, no
    // duplicate runs). Mirrors loop.config.json -> concurrency.singleton_key.
    concurrency: [{ limit: 1, key: "event.data.unit" }],
    onFailure: async ({ error, event, step }) => {
      // Retries exhausted. Nothing is lost — surface it and let the next tick resume.
      await step.run("notify-failure", async () => {
        await notifyHuman(`[orbit] loop failed: ${error.message}. Next tick will resume.`);
      });
    },
  },
  { cron: "0 * * * *" }, // hourly heartbeat — or { event: "orbit/loop.tick" }
  async ({ event, step }) => {
    // READ — fresh each tick (not checkpointed; you want current state).
    const state = await loadState();

    // ACT — delegate to a role as its own durable sub-function. Checkpointed: on resume this
    // is NOT re-invoked, and the model is NOT re-called.
    const result = await step.invoke("act", {
      function: orbitRole,
      data: { role: "orchestrator", goal: state.run_goal, context: state.context },
    });

    // Human-approval checkpoint — propose, never auto-do the irreversible thing.
    if (result.needs_human) {
      await step.run("await-human", async () => {
        await notifyHuman(`[orbit] approval needed: ${result.needs_human}`);
      });
      return { paused: "awaiting human" };
    }

    // EVALUATE — safety (veto) + quality gates. Checkpointed.
    const gates = await step.run("evaluate", async () => evaluateGates(result));
    const passed = gates.input && gates.quality && gates.safety;

    // UPDATE + DECIDE — persist progress; stop on done. (Hard caps: model these with
    // step.sleep / a per-run counter in state, or Inngest throttle/limits per your SDK.)
    await step.run("update-state", async () => saveState({ ...state, lastGates: gates }));
    return { passed, done: passed && goalMet(result, state) };
  },
);

// --- Layer 2: a role as a durable skill --------------------------------------------------
// One concern, retryable, independently invocable. The LLM call is a checkpointed step, so
// a transient failure retries the step without re-running the whole role.
export const orbitRole = inngest.createFunction(
  { id: "orbit-role", retries: 3 },
  { event: "orbit/role.run" },
  async ({ event, step }) => {
    const output = await step.run("think", async () => {
      return await callModel(event.data.role, event.data.goal, event.data.context); // TODO: wire your model
    });
    return output; // { ok, summary, artifacts, tokens, cost_usd, needs_human }
  },
);

// --- seams you wire (kept as stubs so the template is honest, not fake-complete) ---------
async function loadState(): Promise<any> { /* read CLAUDE.md + .orbit/STATE.md */ return {}; }
async function saveState(_s: any): Promise<void> { /* write .orbit/STATE.md */ }
async function callModel(_role: string, _goal: string, _ctx: string): Promise<any> {
  throw new Error("[STUB] wire callModel to your LLM / orchestration");
}
function evaluateGates(_r: any) { return { input: false, quality: false, safety: false }; } // TODO
function goalMet(_r: any, _s: any) { return false; } // TODO
async function notifyHuman(_msg: string): Promise<void> { /* Slack/email/etc. */ }
