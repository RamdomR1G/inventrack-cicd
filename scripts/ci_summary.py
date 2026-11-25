#!/usr/bin/env python3
"""Imprime en Markdown el resultado de reports/junit.xml para el resumen de GitHub Actions.

Uso: python scripts/ci_summary.py "Título" >> "$GITHUB_STEP_SUMMARY"
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from o2_event import junit_summary  # noqa: E402

title = sys.argv[1] if len(sys.argv) > 1 else "Resultado de las pruebas"
path = sys.argv[2] if len(sys.argv) > 2 else "reports/junit.xml"
if not os.path.exists(path):
    print(f"## {title}\nNo se generó el reporte de pruebas (la etapa falló antes de ejecutarlas).")
    sys.exit(0)
s = junit_summary(path)
print(f"## {title}")
print("| Total | Pasaron | Fallaron | Omitidas | Duración |\n|---|---|---|---|---|")
print(f"| {s.get('tests_total', 0)} | {s.get('tests_passed', 0)} | {s.get('tests_failed', 0)} | "
      f"{s.get('tests_skipped', 0)} | {s.get('tests_duration_s', 0)} s |")
if s.get("failed_tests"):
    print("\n**Fallidas:** " + s["failed_tests"])
