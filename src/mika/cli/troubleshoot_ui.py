from __future__ import annotations

import json

from rich.console import Console

from mika.cli.render import render_diagnosis
from mika.cli.session import ChatSession
from mika.router.discovery import discover
from mika.troubleshoot.workflow import troubleshoot_problem
from mika.utils.printer import log_error, status_spinner


async def run_troubleshoot(problem_description: str, session: ChatSession, console: Console) -> str | None:
    """Diagnose problem_description and render the result.

    Returns a composed follow-up request text if the user confirms applying
    the recommended fixes, otherwise None.
    """
    client = session.require_router()

    try:
        with status_spinner("Reading router state..."):
            ctx = await discover(client)
        with status_spinner("Diagnosing problem..."):
            diagnosis = await troubleshoot_problem(problem_description, client, ctx)
    except Exception as exc:
        log_error(f"Troubleshooting failed: {exc}")
        return None

    render_diagnosis(console, diagnosis)

    summary = diagnosis.problem_description
    if diagnosis.recommended_fixes:
        summary += " | Fixes: " + "; ".join(diagnosis.recommended_fixes)
    session.add_history(
        "assistant", summary, render_kind="troubleshoot",
        render_payload=json.dumps(diagnosis.model_dump(mode="json"), default=str),
    )

    if not diagnosis.recommended_fixes:
        return None

    try:
        apply = console.input("Apply the recommended fixes? [y/N] ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        apply = False
    if not apply:
        return None

    fixes = "; ".join(diagnosis.recommended_fixes)
    return f"Fix the following issue on the router: {problem_description}. Apply these recommended fixes: {fixes}"
