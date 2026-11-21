"""
Quality checks for the CV assistant against the real model.

Sends each case in cases.json through the Flask app (same prompts, language
detection and job-offer mode as production) and checks the answer with simple
rules: reply language, required facts, forbidden content (phone, invented
years, salary figures) and refusing off-topic requests.

Usage:
    GROQ_API_KEY=gsk_... python evals/run_evals.py            # all cases
    python evals/run_evals.py --only phone,offtopic-code       # some cases
    python evals/run_evals.py --delay 4                        # slower, for free-tier limits

Exit code 1 if any case fails, so it can run in CI.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the app loads docs/ relative to the repo root
os.environ.setdefault("STATS_DB", str(ROOT / "evals" / ".evals-stats.db"))

import app  # noqa: E402

OFF_TOPIC_MAX_CHARS = 400
OFF_TOPIC_LEAKS = re.compile(r"```|\bdef \w+\(|apiVersion:|\bkubectl\b|\bsorted\(|\bEspaña\b|\bSpain\b")


def check(case: dict, answer: str) -> list[str]:
    problems = []
    low = answer.lower()
    detected = app.detect_lang(answer)
    if case.get("lang") and detected and detected != case["lang"]:
        problems.append(f"idioma {detected}, esperado {case['lang']}")
    anys = case.get("must_contain_any")
    if anys and not any(s.lower() in low for s in anys):
        problems.append(f"no contiene ninguno de {anys}")
    for s in case.get("must_contain_all", []):
        if s.lower() not in low:
            problems.append(f"falta «{s}»")
    for pattern in case.get("must_not_match", []):
        if re.search(pattern, answer, re.I):
            problems.append(f"contiene /{pattern}/")
    if case.get("min_chars") and len(answer) < case["min_chars"]:
        problems.append(f"muy corta ({len(answer)} < {case['min_chars']})")
    if case.get("off_topic"):
        if len(answer) > OFF_TOPIC_MAX_CHARS:
            problems.append(f"fuera de tema pero respondió largo ({len(answer)} caracteres)")
        if OFF_TOPIC_LEAKS.search(answer):
            problems.append("fuera de tema pero dio la respuesta")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between calls")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every answer")
    args = ap.parse_args()

    cases = json.loads((ROOT / "evals" / "cases.json").read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    client = app.app.test_client()
    failures = 0
    for i, case in enumerate(cases):
        if i:
            time.sleep(args.delay)
        app._answer_cache.clear()  # always hit the model
        res = client.post("/chat", json={"question": case["question"], "mode": case.get("mode", "chat")},
                          environ_base={"REMOTE_ADDR": f"eval-{i}"})
        data = res.get_json() or {}
        if data.get("rate_limited") or "error" in data:
            print(f"⚠  {case['id']:<22} sin respuesta del modelo: {data.get('reset_msg') or data.get('error')}")
            failures += 1
            continue
        answer = data.get("answer", "")
        problems = check(case, answer)
        mark = "✅" if not problems else "❌"
        print(f"{mark} {case['id']:<22} {'; '.join(problems)}")
        if problems or args.verbose:
            print("   " + answer.replace("\n", "\n   ")[:1500] + "\n")
        failures += bool(problems)

    print(f"\n{len(cases) - failures}/{len(cases)} casos correctos")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
