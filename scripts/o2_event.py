#!/usr/bin/env python3
"""Envía un evento del pipeline CI/CD a OpenObserve (API HTTP/JSON, stream `cicd_pipeline`).

Uso:
    python scripts/o2_event.py <event_type> <status> [--junit reports/junit.xml] [--message "..."]

event_type: test_result | deploy | deploy_blocked
status:     success | failure | cancelled | blocked

Lee del entorno las variables que GitHub Actions define (GITHUB_SHA, GITHUB_REF_NAME,
GITHUB_ACTOR, ...) y las credenciales O2_URL, O2_USER, O2_PASSWORD. Si faltan las
credenciales, solo imprime el evento: nunca hace fallar el pipeline.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def junit_summary(path):
    if not path or not os.path.exists(path):
        return {}
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = sum(int(s.get("tests", 0)) for s in suites)
    failures = sum(int(s.get("failures", 0)) for s in suites)
    errors = sum(int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    duration = sum(float(s.get("time", 0)) for s in suites)
    failed = [f"{c.get('classname')}::{c.get('name')}" for c in root.iter("testcase")
              if c.find("failure") is not None or c.find("error") is not None]
    return {"tests_total": total, "tests_passed": total - failures - errors - skipped,
            "tests_failed": failures + errors, "tests_skipped": skipped,
            "tests_duration_s": round(duration, 2), "failed_tests": ", ".join(failed[:20])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("event_type")
    ap.add_argument("status")
    ap.add_argument("--junit")
    ap.add_argument("--message", default="")
    ap.add_argument("--extra", default="{}", help="JSON con campos adicionales")
    a = ap.parse_args()

    env = os.environ.get
    server, repo, run_id = env("GITHUB_SERVER_URL", "https://github.com"), env("GITHUB_REPOSITORY", ""), env("GITHUB_RUN_ID", "")
    sha = env("GITHUB_SHA", "")
    event = {
        "_timestamp": int(time.time() * 1_000_000),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": a.event_type,
        "status": a.status,
        "level": "error" if a.status in ("failure", "blocked") else "info",
        "message": a.message,
        "commit_sha": sha,
        "commit_short": sha[:7],
        "commit_message": env("COMMIT_MESSAGE", "").splitlines()[0][:200] if env("COMMIT_MESSAGE") else "",
        "branch": env("GITHUB_HEAD_REF") or env("GITHUB_REF_NAME", ""),
        "actor": env("GITHUB_ACTOR", ""),
        "trigger": env("GITHUB_EVENT_NAME", ""),
        "repository": repo,
        "workflow": env("GITHUB_WORKFLOW", ""),
        "job": env("GITHUB_JOB", ""),
        "run_id": run_id,
        "run_attempt": env("GITHUB_RUN_ATTEMPT", ""),
        "run_url": f"{server}/{repo}/actions/runs/{run_id}" if repo else "",
        "runner_os": env("RUNNER_OS", ""),
    }
    event.update(junit_summary(a.junit))
    event.update(json.loads(a.extra))
    print(json.dumps(event, indent=2, ensure_ascii=False))

    url, user, pwd = env("O2_URL", "").rstrip("/"), env("O2_USER", ""), env("O2_PASSWORD", "")
    if not (url and user and pwd):
        print("::warning::O2_URL/O2_USER/O2_PASSWORD no definidos: el evento no se envió a OpenObserve")
        return 0
    req = urllib.request.Request(
        f"{url}/api/default/cicd_pipeline/_json", data=json.dumps([event]).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                print(f"OpenObserve respondió {r.status}: {r.read().decode()[:300]}")
                return 0
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"::warning::Intento {attempt + 1} de enviar el evento a OpenObserve falló: {e}")
            time.sleep(3)
    return 0  # la observabilidad no debe tumbar el pipeline


if __name__ == "__main__":
    sys.exit(main())
