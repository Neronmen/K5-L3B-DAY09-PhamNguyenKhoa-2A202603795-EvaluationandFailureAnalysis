"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def _looser(new: dict | None, old: dict | None) -> str | None:
    """Why `new` is a looser threshold than `old`, or None. Works on metric thresholds and on slices
    (which keep min / no_significant_drop at the top level)."""
    new, old = new or {}, old or {}
    for key in ("max", "max_increase"):
        if key in old and (key not in new or new[key] > old[key]):
            return f"{key} {old[key]} -> {new.get(key)}"
    if "min" in old and ("min" not in new or new["min"] < old["min"]):
        return f"min {old['min']} -> {new.get('min')}"
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        return "no_significant_drop removed"
    return None


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    from lab9.graders import GRADERS
    problems: list[str] = []
    metrics = pr.get("metrics") or {}
    rows, brows = pr.get("rows") or [], base.get("rows") or []
    man, bman = pr.get("manifest") or {}, base.get("manifest") or {}

    # 1. NaN / inf metric values (nan < min is False, so a naive gate lets them through)
    for k, v in metrics.items():
        if isinstance(v, float) and not math.isfinite(v):
            problems.append(f"metric {k} is {v}")
    # 2. row count = items x seeds, no duplicated (item, seed)
    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {want} (items x seeds)")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item, seed) row(s)")
    # 3. same (item, seed) set and same seeds/items as the baseline (cherry-picked seeds or items)
    bkeys = {(r.get("item_id"), r.get("seed")) for r in brows}
    if set(keys) != bkeys:
        problems.append(f"(item, seed) set differs from baseline: {len(bkeys - set(keys))} missing, "
                        f"{len(set(keys) - bkeys)} extra")
    if sorted(man.get("seeds") or []) != sorted(bman.get("seeds") or []):
        problems.append(f"seeds {man.get('seeds')} differ from baseline {bman.get('seeds')}")
    if man.get("items") != bman.get("items"):
        problems.append(f"manifest items {man.get('items')} differ from baseline {bman.get('items')}")
    # 4. crashed graders: reported failures, or graded values that silently became None
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s) on this run")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    nones = sum(1 for r in rows for m in graded if r.get(m) is None)
    if nones:
        problems.append(f"{nones} graded value(s) are None (grader crash or dropped score)")
    # 5. reported metrics must match what the rows give (hand-edited metrics)
    for m in graded:
        vals = [r[m] for r in rows if r.get(m) is not None]
        rep = metrics.get(m)
        if not vals or not isinstance(rep, (int, float)) or not math.isfinite(rep):
            continue
        again = sum(vals) if m in ("secret_leak", "approval_bypass") else sum(vals) / len(vals)
        if abs(rep - again) > 1e-3:
            problems.append(f"metric {m} reported {rep} but rows give {again:.4f}")
    # 6. an item's slice tags must not change (relabelling an item out of a slice hides it)
    btags = {r.get("item_id"): sorted(r.get("slices") or []) for r in brows}
    moved = sorted({r.get("item_id") for r in rows
                    if r.get("item_id") in btags and sorted(r.get("slices") or []) != btags[r.get("item_id")]})
    if moved:
        problems.append(f"slice tags changed vs baseline for {', '.join(moved[:5])}")
    # 7. ratchet: on the same eval-set version thresholds may only get stricter
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        new = {m["id"]: m for m in spec.get("metrics", [])}
        for mid, old in {m["id"]: m for m in base_spec.get("metrics", [])}.items():
            if mid not in new:
                problems.append(f"ratchet: metric {mid} removed")
                continue
            if old.get("blocking") and not new[mid].get("blocking"):
                problems.append(f"ratchet: metric {mid} no longer blocking")
            why = _looser(new[mid].get("threshold"), old.get("threshold"))
            if why:
                problems.append(f"ratchet: metric {mid} {why}")
        new_s = {(x["name"], x["metric"]): x for x in spec.get("slices") or []}
        for key, old in {(x["name"], x["metric"]): x for x in base_spec.get("slices") or []}.items():
            cur = new_s.get(key)
            if cur is None:
                problems.append(f"ratchet: slice {key[0]}/{key[1]} removed")
                continue
            if old.get("blocking") and not cur.get("blocking"):
                problems.append(f"ratchet: slice {key[0]}/{key[1]} no longer blocking")
            why = _looser(cur, old)
            if why:
                problems.append(f"ratchet: slice {key[0]}/{key[1]} {why}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                    # an empty slice is not a passing slice
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if s.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<40} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
