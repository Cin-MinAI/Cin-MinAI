# SPDX-License-Identifier: GPL-3.0-or-later
"""Benchmark the setup this project runs, in AICUI's terminal (its Benchmark button):

    python3 -P -m cin_minai.aicui.bench FOLDER

The local models of the project's team — one model, or team B's two (also as the cloud lead's contributors) — loaded
as planned at 32K, 48K, 64K, 96K and 128K in turn, until one fails: each filled to about nine tenths with text and
asked one question. Whether it held, the card's memory at its peak, and the speeds are printed, stored
(inference/benchmark.py) for the Context options, and sent to AICUI's chat. Ctrl+C stops it; what's measured stays."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time

from cin_minai.inference import benchmark, contextfit, matcher

SENTENCE = ("The river turned east past the old mill, where the miller kept a ledger of every sack of grain, the "
            "weather of each morning and the names of travellers who asked the way to the northern pass. ")


def card_used_mib() -> int | None:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        return int(out[0]) if out else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


class Peak:
    """The card's memory in use at its highest while a size is measured (NVIDIA cards; None elsewhere)."""

    def __init__(self) -> None:
        self.mib, self.stop = card_used_mib(), threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self) -> None:
        while not self.stop.wait(1.0):
            now = card_used_mib()
            if now is not None:
                self.mib = max(self.mib or 0, now)

    def done(self) -> int | None:
        self.stop.set()
        self.thread.join(3)
        return self.mib


def tokens(backend, text: str) -> int:
    """How many tokens the model's own tokenizer makes of text (llama-server's /tokenize)."""
    from cin_minai.inference.llamacpp import UnixHTTPConnection
    c = UnixHTTPConnection(backend.sock, 60)
    try:
        c.request("POST", "/tokenize", body=json.dumps({"content": text}).encode(),
                  headers={"Content-Type": "application/json"})
        return len(json.loads(c.getresponse().read()).get("tokens", []))
    finally:
        c.close()


def fill(backend, ctx: int) -> dict:
    """The model filled to about nine tenths of ctx and asked one question: what it read and wrote, and how fast."""
    backend.load()
    st = backend.status()
    if st.context != ctx or st.reduced:
        raise RuntimeError(f"it loaded only at {st.context // 1024}K ({st.reduced or 'a smaller setting'})")
    per = max(1, tokens(backend, SENTENCE))
    text = SENTENCE * max(1, int(ctx * 0.9 - 300) // per)
    start = time.monotonic()
    answer, timings = backend.chat([{"role": "user", "content": text + "\nIn one sentence: what is this text about?"}],
                                   max_tokens=48)
    t = timings[-1] if isinstance(timings, list) and timings else timings or {}
    if not int(t.get("prompt_n") or 0) or not answer.strip():  # a stream that ended quietly: it never answered
        for _ in range(40):  # (2026-10-14: 64K "held" with nothing read — the server had dumped core)
            if not backend.alive():
                break
            time.sleep(0.25)
        raise RuntimeError("the model stopped while reading (out of graphics memory, most likely)"
                           if not backend.alive() else "it gave no answer")
    return {"read": int(t.get("prompt_n") or 0), "prompt_tps": round(float(t.get("prompt_per_second") or 0), 1),
            "gen_tps": round(float(t.get("predicted_per_second") or 0), 1),
            "seconds": round(time.monotonic() - start, 1), "answer": answer.strip()[:120]}


def the_setup(root: str):
    """The project's local models: ("pair", junior, senior) or ("one", plan, Model), from its team (and the cloud
    lead's crew)."""
    from cin_minai.daemon.models import ModelStore
    from cin_minai.inference import cloud

    from .pair import JUNIOR_FILE, SENIOR_FILE, team_of
    store = ModelStore()
    machine = matcher.read_machine(models_dir=store.root)
    cs = cloud.settings(root)
    two = (cs["role"] == "lead" and cs.get("crew") == "two") or (cs["role"] != "lead" and team_of(root) == "B")
    if two:
        j = contextfit.model_for(JUNIOR_FILE, store.path(JUNIOR_FILE))
        s = contextfit.model_for(SENIOR_FILE, store.path(SENIOR_FILE))
        return store, machine, ("pair", (JUNIOR_FILE, j), (SENIOR_FILE, s))
    ours = matcher.match(machine).get("coding")
    plan = store.in_use("coding") or ours
    if not plan:
        raise SystemExit("No coding model runs on this computer yet.")
    return store, machine, ("one", plan, contextfit.model_for(plan["file"], store.path(plan["file"])))


def backend_for(store, plan: dict, file: str, sock: str, log):
    from cin_minai.daemon import config
    from cin_minai.daemon.models import backend_cfg
    from cin_minai.inference.llamacpp import LlamaCppBackend
    cfg = backend_cfg(config.load()["inference"], plan, store.path(file))
    cfg["socket_name"] = sock

    class OneSize(LlamaCppBackend):
        def ladder(self):  # the size being measured only: no smaller fallback
            return super().ladder()[:1]
    return OneSize(cfg, log)


def run(root: str, say=print, sizes=benchmark.LADDER) -> list[str]:
    from .agent import unload_guide
    unload_guide()
    store, machine, setup = the_setup(root)
    card = benchmark.card_of(machine)
    log_path = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cinminai",
                            "code-server.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(msg: str) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} bench {msg}\n")
    lines = []
    if setup[0] == "one":
        _, plan0, m = setup
        files, names = [plan0["file"]], [plan0["model"]]
    else:
        (jf, j), (sf, s) = setup[1], setup[2]
        files, names = [jf, sf], [j.name, s.name]
    key = benchmark.setup_key(files, card)
    say(f"\033[1mBenchmark: {' and '.join(names)} on {card or 'the processor'}; each size is filled to about nine "
        "tenths and asked one question. Ctrl+C stops; what's measured stays.\033[0m")
    for ctx in sizes:
        if setup[0] == "one":
            p = matcher.full_plan(m, machine, ctx, plan0.get("why", ""))
            plans = [p] if p else None
        else:
            pp = matcher.pair_plan(j, s, machine, ctx, ctx)
            plans = [pp["junior"], pp["senior"]] if pp else None
        label = f"{ctx // 1024}K"
        if not plans:
            say(f"  {label}: doesn't fit this card by Cin-MinAI's plan; the benchmark stops here.")
            lines.append(f"{label}: doesn't fit by the plan")
            break
        backends = [backend_for(store, p, f, sock, log)
                    for p, f, sock in zip(plans, files, ("llama-code.sock", "llama-senior.sock"))]
        peak, results, why = Peak(), [], ""
        say(f"  {label}: {', '.join(p['mode'] for p in plans)} — loading and reading…")
        try:
            for b in backends:  # a pair: both loaded, each filled in turn (the first is placed first)
                b.load()
            for b in backends:
                results.append(fill(b, ctx))
        except KeyboardInterrupt:
            for b in backends:
                b.unload()
            peak.done()
            say("  stopped.")
            break
        except Exception as e:  # out of memory, a crash, a load that fell short
            why = str(e)[:200]
        mib = peak.done()
        for b in backends:
            b.unload()
        if why:
            benchmark.record(key, [ctx] * len(files), False, why=why, card_mib=mib)
            say(f"\033[33m  {label}: failed — {why}\033[0m")
            lines.append(f"{label}: failed ({why[:80]})")
            break
        r = results[-1]
        benchmark.record(key, [ctx] * len(files), True, card_mib=mib, prompt_tps=r["prompt_tps"],
                         gen_tps=r["gen_tps"], seconds=sum(x["seconds"] for x in results),
                         read=sum(x["read"] for x in results))
        speeds = "; ".join(f"{n}: read {x['read']:,} tokens at {x['prompt_tps']:.0f}/s, wrote {x['gen_tps']:.1f} words/s"
                           for n, x in zip(names, results))
        say(f"\033[32m  {label}: held — {speeds}; the card at {mib or '?'} MiB at its peak\033[0m")
        lines.append(f"{label}: held ({speeds})")
    summary = benchmark.summary(key)
    say(f"\033[1m{summary}\033[0m The Context options use this from now on.")
    # then the model that works as the junior (the one model, or team B's Junior): its limits per task
    jfile, jmodel, jname = (plan0["file"], m, plan0["model"]) if setup[0] == "one" else (jf, j, j.name)
    coding = coding_run(store, machine, jfile, jmodel, jname, say) if jmodel is not None else []
    return [summary, *lines, *coding]


def coding_run(store, machine, file: str, m, name: str, say=print, targets=None) -> list[str]:
    """How much load the model carries as a junior (benchcode.py): one project grows — ~100 lines, then +200 holding
    them, +400, +800… — each stage a fresh task, until one fails (if the first fails: 50 lines instead). Each stage
    is checked by us: new code, earlier code held, changed code, the report that calls it all."""
    import shutil
    import tempfile

    from . import benchcode
    from .agent import Agent
    card = benchmark.card_of(machine)
    ctx, _ = contextfit.fit(m, machine, {"choice": "fill"})  # the most it can hold here, as measured above
    (ctx,), _ = benchmark.cap([ctx], benchmark.setup_key([file], card))
    plan = matcher.full_plan(m, machine, ctx)
    if not plan:
        return ["coding run: the model doesn't fit this card"]
    backend = backend_for(store, plan, file, "llama-code.sock", lambda msg: None)
    benchmark.reset_coding(file, card)  # this run replaces the last one
    written = {"tokens": 0}

    def counted(messages, **kw):  # the words it writes, for efficiency (tokens a line)
        text, timings = backend.chat(messages, **kw)
        t = timings[-1] if isinstance(timings, list) and timings else timings or {}
        written["tokens"] += int(t.get("predicted_n") or 0)
        return text, timings
    lines = []
    say(f"\033[1mCoding run: {name} as a junior, at {ctx // 1024}K — one project grows (~100 lines, then +200, +400, "
        "+800…) and every stage must keep everything before it working. Ctrl+C stops it.\033[0m")
    targets = list(targets or benchcode.TARGETS)
    root = tempfile.mkdtemp(prefix="cinminai-bench-")
    project, first, fallback = benchcode.Project(root), True, False
    try:
        while targets:
            target = targets.pop(0)
            before, start, tokens0 = project.lines(), time.monotonic(), written["tokens"]
            task = project.grow(target)
            new_types = len([e for e in project.ents if e["stage"] == project.stage])
            junior = Agent(root, counted, name, "auto", ctx=ctx, say=lambda s: None)  # fresh: the protocol
            junior.role, junior.max_steps = "junior", min(400, 30 + 6 * new_types)
            try:
                junior.work(task, None)
            except Exception as e:  # the model server failed: the stage failed
                say(f"\033[33m  stage {project.stage}: the model stopped ({str(e)[:120]})\033[0m")
            res = project.check()
            total = project.lines()
            steps = 1 + len([s for s in getattr(junior, "steps", []) if isinstance(s, dict) and s.get("did")])
            seconds, tokens = round(time.monotonic() - start), written["tokens"] - tokens0
            added = max(0, total - before)
            kinds = {k: res[k] for k in ("new", "held", "changed", "report") if k in res}
            benchmark.record_coding(file, card, (0 if fallback else project.stage), res["ok"], target=target,
                                    total=total, added=added, steps=steps, seconds=seconds, tokens=tokens,
                                    context=ctx, why=res.get("why", "")[:200], **kinds)
            said = (f"stage {project.stage}: {'held' if res['ok'] else 'failed'} — {total:,} lines in all (+{added:,} "
                    f"written), {', '.join(f'{k} {v}' for k, v in kinds.items())}; {steps} steps, {seconds // 60} min "
                    f"{seconds % 60} s" + (f", {tokens / max(1, added):.0f} tokens a line" if added else ""))
            say(("\033[32m  " if res["ok"] else "\033[33m  ") + said + "\033[0m")
            lines.append(said)
            if not res["ok"]:
                if first and not fallback:  # too much to start with: a smaller first step, on a fresh project
                    shutil.rmtree(root, ignore_errors=True)
                    root = tempfile.mkdtemp(prefix="cinminai-bench-")
                    project, fallback, targets = benchcode.Project(root), True, [benchcode.FIRST_FALLBACK]
                    say(f"  the first stage failed: {benchcode.FIRST_FALLBACK} lines instead.")
                    continue
                break
            first = False
    except KeyboardInterrupt:
        say("  stopped.")
    finally:
        backend.unload()
        shutil.rmtree(root, ignore_errors=True)
    lim = benchmark.coding_limits(file, card)
    summary = (f"Junior load for {name}: carries {lim['capacity']:,} lines in all; {lim['lines']} lines and "
               f"{lim['steps']} steps a task" + (" (measured)." if lim["measured"] else " (stand-ins: no stage held)."))
    say(f"\033[1m{summary}\033[0m")
    return [summary, *lines]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = os.path.abspath(argv[0] if argv else os.getcwd())
    from .project import project_root
    root = project_root(root)
    try:
        lines = run(root)
    except (Exception, SystemExit) as e:
        lines = [f"The benchmark couldn't run: {e}"]
        print(f"\033[33m{lines[0]}\033[0m")
    events = os.path.join(root, ".cinminai", "events.jsonl")
    os.makedirs(os.path.dirname(events), exist_ok=True)
    with open(events, "a", encoding="utf-8") as f:  # AICUI's chat shows it
        f.write(json.dumps({"t": time.time(), "kind": "bench", "text": "Benchmark of this setup:\n" + "\n".join(lines)})
                + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
