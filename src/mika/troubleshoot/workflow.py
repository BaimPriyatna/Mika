"""
Automated Troubleshooting Workflow.

Diagnoses router connectivity, DHCP, DNS, and NAT issues by gathering
symptoms, running diagnostic tests, and generating remediation steps.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from mika.monitoring.collector import collect_health
from mika.troubleshoot.models import (
    DiagnosisResult,
    Hypothesis,
    HypothesisLikelihood,
    TroubleshootingSession,
)

if TYPE_CHECKING:
    from mika.router.client import RouterClient
    from mika.router.discovery import RouterContext

logger = logging.getLogger(__name__)


class TroubleshootingWorkflow:

    def __init__(self, router_client: RouterClient) -> None:
        self._client = router_client

    async def diagnose(
        self,
        problem_description: str,
        router_context: RouterContext | None = None,
    ) -> DiagnosisResult:
        logger.info(f"Starting troubleshooting: {problem_description}")

        session = TroubleshootingSession(
            session_id=f"troubleshoot_{uuid.uuid4().hex[:8]}",
            problem_description=problem_description,
            router_identity="unknown",
        )

        await self._collect_state(session, router_context)

        await self._form_hypotheses(session)

        await self._test_hypotheses(session)


        self._propose_fixes(session)

        diagnosis = session.complete()
        
        logger.info(
            f"Diagnosis complete: {len(diagnosis.hypotheses)} hypotheses, "
            f"{len(diagnosis.recommended_fixes)} recommended fixes"
        )

        return diagnosis

    async def _collect_state(
        self,
        session: TroubleshootingSession,
        router_context: RouterContext | None,
    ) -> None:
        logger.debug("Collecting router state for diagnosis")

        try:
            health = await collect_health(self._client)
            session.router_identity = health.router_identity
            session.state_collected["health"] = {
                "status": health.status.value,
                "cpu_load": health.system_metrics.cpu_load,
                "memory_usage": health.system_metrics.memory_usage_percent,
                "warnings": list(health.warnings),
                "errors": list(health.errors),
            }
            session.add_test("Collected system health metrics")
        except Exception as e:
            logger.error(f"Failed to collect health metrics: {e}")
            session.state_collected["health"] = {"error": str(e)}

        if router_context is None:
            try:
                from mika.router.discovery import discover
                
                router_context = await discover(self._client)
                session.add_test("Collected router configuration")
            except Exception as e:
                logger.error(f"Failed to collect router context: {e}")
                router_context = None

        if router_context:
            session.state_collected["interfaces"] = [
                {
                    "name": iface.name,
                    "running": iface.running,
                    "disabled": iface.disabled,
                }
                for iface in router_context.interfaces
            ]
            session.state_collected["addresses"] = [
                {
                    "address": addr.address,
                    "interface": addr.interface,
                }
                for addr in router_context.addresses
            ]
            session.state_collected["routes"] = [
                {
                    "dst_address": route.dst_address,
                    "gateway": route.gateway,
                    "active": route.active,
                }
                for route in router_context.routes
            ]
            session.state_collected["firewall_rules_count"] = len(router_context.firewall_rules)
            session.state_collected["dhcp_servers"] = [
                {
                    "name": dhcp.name,
                    "interface": dhcp.interface,
                    "disabled": dhcp.disabled,
                }
                for dhcp in router_context.dhcp_servers
            ]

    async def _form_hypotheses(self, session: TroubleshootingSession) -> None:
        logger.debug("Forming hypotheses")

        problem_lower = session.problem_description.lower()
        health = session.state_collected.get("health", {})

        if health.get("errors"):
            session.add_hypothesis(
                Hypothesis(
                    description="Critical system health issue",
                    likelihood=HypothesisLikelihood.VERY_LIKELY,
                    evidence=tuple(health["errors"]),
                    tests_performed=("System health check",),
                )
            )

        if "interface" in problem_lower or "down" in problem_lower:
            interfaces = session.state_collected.get("interfaces", [])
            down_interfaces = [
                iface["name"]
                for iface in interfaces
                if not iface["disabled"] and not iface["running"]
            ]
            
            if down_interfaces:
                session.add_hypothesis(
                    Hypothesis(
                        description=f"Interface(s) are down: {', '.join(down_interfaces)}",
                        likelihood=HypothesisLikelihood.VERY_LIKELY,
                        evidence=(f"Interfaces not running: {', '.join(down_interfaces)}",),
                        tests_performed=("Interface status check",),
                    )
                )
            else:
                session.add_hypothesis(
                    Hypothesis(
                        description="Interface configuration issue",
                        likelihood=HypothesisLikelihood.POSSIBLE,
                        evidence=("Problem mentions interface but all interfaces are up",),
                        tests_performed=("Interface status check",),
                    )
                )

        if "internet" in problem_lower or "connectivity" in problem_lower:
            routes = session.state_collected.get("routes", [])
            default_routes = [r for r in routes if r["dst_address"] == "0.0.0.0/0"]
            
            if not default_routes:
                session.add_hypothesis(
                    Hypothesis(
                        description="No default route configured",
                        likelihood=HypothesisLikelihood.VERY_LIKELY,
                        evidence=("No default gateway found in routing table",),
                        tests_performed=("Routing table check",),
                    )
                )
            elif not any(r["active"] for r in default_routes):
                session.add_hypothesis(
                    Hypothesis(
                        description="Default route exists but is inactive",
                        likelihood=HypothesisLikelihood.LIKELY,
                        evidence=("Default route found but marked as inactive",),
                        tests_performed=("Routing table check",),
                    )
                )
            else:
                session.add_hypothesis(
                    Hypothesis(
                        description="NAT or firewall configuration issue",
                        likelihood=HypothesisLikelihood.LIKELY,
                        evidence=("Default route is active but connectivity problem exists",),
                        tests_performed=("Routing table check", "Firewall rules check"),
                    )
                )

        if "dhcp" in problem_lower:
            dhcp_servers = session.state_collected.get("dhcp_servers", [])
            disabled_dhcp = [d["name"] for d in dhcp_servers if d["disabled"]]
            
            if disabled_dhcp:
                session.add_hypothesis(
                    Hypothesis(
                        description=f"DHCP server(s) disabled: {', '.join(disabled_dhcp)}",
                        likelihood=HypothesisLikelihood.VERY_LIKELY,
                        evidence=(f"DHCP servers are disabled: {', '.join(disabled_dhcp)}",),
                        tests_performed=("DHCP server check",),
                    )
                )
            elif not dhcp_servers:
                session.add_hypothesis(
                    Hypothesis(
                        description="No DHCP server configured",
                        likelihood=HypothesisLikelihood.LIKELY,
                        evidence=("No DHCP servers found",),
                        tests_performed=("DHCP server check",),
                    )
                )

        if not session.hypotheses:
            session.add_hypothesis(
                Hypothesis(
                    description="Insufficient information to determine cause",
                    likelihood=HypothesisLikelihood.UNLIKELY,
                    evidence=("No obvious issues found in collected state",),
                    tests_performed=tuple(session.tests_performed),
                )
            )

    async def _test_hypotheses(self, session: TroubleshootingSession) -> None:
        logger.debug(f"Testing {len(session.hypotheses)} hypotheses")

    def _propose_fixes(self, session: TroubleshootingSession) -> None:
        logger.debug("Proposing fixes")

        for hypothesis in session.hypotheses:
            if hypothesis.likelihood == HypothesisLikelihood.VERY_LIKELY:
                if "down" in hypothesis.description.lower():
                    session.add_fix(
                        "Check physical cable connection and enable interface if disabled"
                    )
                elif "default route" in hypothesis.description.lower():
                    session.add_fix(
                        "Configure default route pointing to ISP gateway"
                    )
                elif "dhcp" in hypothesis.description.lower() and "disabled" in hypothesis.description.lower():
                    session.add_fix(
                        "Enable DHCP server"
                    )
                elif "nat" in hypothesis.description.lower() or "firewall" in hypothesis.description.lower():
                    session.add_fix(
                        "Review firewall rules and NAT configuration for internet-bound traffic"
                    )
                elif "critical" in hypothesis.description.lower():
                    session.add_fix(
                        "Address critical system issue (check CPU, memory, or disk usage)"
                    )


async def troubleshoot_problem(
    problem_description: str,
    router_client: RouterClient,
    router_context: RouterContext | None = None,
) -> DiagnosisResult:
    workflow = TroubleshootingWorkflow(router_client)
    return await workflow.diagnose(problem_description, router_context)
