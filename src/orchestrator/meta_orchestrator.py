"""
NEXUS Meta-Orchestrator (ARCH-014)

Coordinates multiple Nexus instances for microservices architectures.
Decomposes a high-level directive into per-service requirements, spawns
child Nexus graph executions for each service, coordinates inter-service
contracts, and generates Docker Compose configuration.

Usage:
    meta = MetaOrchestrator(["api", "frontend", "worker"])
    result = await meta.orchestrate_multi_service("Build a food delivery app")
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field

import yaml  # type: ignore[import-untyped]

from src.agents.sdk_bridge import run_planning_agent
from src.orchestrator.graph import AGENTS, compile_nexus_dynamic
from src.orchestrator.state import NexusState

logger = logging.getLogger("nexus.meta_orchestrator")


@dataclass
class ServiceSpec:
    """Specification for a single service within a multi-service directive."""

    name: str
    responsibility: str = ""
    stack: str = ""
    data_owned: str = ""
    apis_exposed: list[str] = field(default_factory=list)
    apis_consumed: list[str] = field(default_factory=list)


@dataclass
class ServiceInstance:
    """A running (or completed) child Nexus instance for one service."""

    name: str
    spec: ServiceSpec
    session_id: str = ""
    port: int = 0
    env_vars: dict[str, str] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    result: dict | None = None


class MetaOrchestrator:
    """Coordinates multiple Nexus instances for microservices architectures."""

    # Default port range for generated services
    _BASE_PORT = 3000

    def __init__(self, services: list[str] | None = None):
        self.services: list[str] = services or []
        self.instances: dict[str, ServiceInstance] = {}
        self._project_path = os.environ.get(
            "NEXUS_PROJECT_PATH", os.path.expanduser("~/Projects/nexus")
        )

    async def orchestrate_multi_service(self, directive: str) -> dict:
        """Run the full meta-orchestration pipeline.

        1. Decompose directive into per-service requirements
        2. Spawn child Nexus instance for each service
        3. Coordinate inter-service contracts (API definitions)
        4. Build services (parallel graph execution)
        5. Generate Docker Compose for all services
        6. Run integration tests across services
        """
        logger.info(
            "Meta-orchestration starting: %d service(s), directive='%s'",
            len(self.services),
            directive[:80],
        )

        # Phase 1: Decompose
        service_specs = await self._decompose_to_services(directive)

        # Phase 2: Spawn instances
        for service_name, spec in service_specs.items():
            instance = self._create_instance(service_name, spec)
            self.instances[service_name] = instance

        # Phase 3: Coordinate contracts
        contracts = await self._coordinate_contracts()

        # Phase 4: Build services (parallel graph execution)
        results = await self._build_services(directive)

        # Phase 5: Integration
        docker_compose = self._generate_docker_compose()

        # Phase 6: Integration tests
        integration_results = await self._run_integration_tests()

        return {
            "status": "complete",
            "services": {name: inst.result for name, inst in self.instances.items()},
            "contracts": contracts,
            "docker_compose": docker_compose,
            "integration_tests": integration_results,
            "service_count": len(self.instances),
        }

    # ------------------------------------------------------------------
    # Phase 1: Decompose directive into services
    # ------------------------------------------------------------------

    async def _decompose_to_services(self, directive: str) -> dict[str, ServiceSpec]:
        """Use CEO agent to decompose into microservices."""
        services_hint = ", ".join(self.services) if self.services else "auto-detect"

        result = await run_planning_agent(
            "ceo",
            AGENTS["ceo"],
            f"""Decompose this directive into microservices:

{directive}

Requested services: {services_hint}

For each service, define:
- service_name (short lowercase identifier, e.g. api, frontend, worker)
- responsibility (one sentence)
- stack (primary framework/language)
- data_owned (what data this service owns)
- apis_exposed (list of API endpoints this service exposes)
- apis_consumed (list of API endpoints this service calls on other services)

Output ONLY a JSON object mapping service names to their specs:
{{
    "api": {{"responsibility": "...", "stack": "FastAPI", "data_owned": "...", "apis_exposed": [...], "apis_consumed": [...]}},
    "frontend": {{"responsibility": "...", "stack": "React", "data_owned": "...", "apis_exposed": [...], "apis_consumed": [...]}}
}}""",
        )

        specs: dict[str, ServiceSpec] = {}
        try:
            raw = result.output
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                for name, data in parsed.items():
                    if isinstance(data, dict):
                        specs[name] = ServiceSpec(
                            name=name,
                            responsibility=data.get("responsibility", ""),
                            stack=data.get("stack", ""),
                            data_owned=data.get("data_owned", ""),
                            apis_exposed=data.get("apis_exposed", []),
                            apis_consumed=data.get("apis_consumed", []),
                        )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse service decomposition: %s", exc)

        # Fallback: create specs from the explicit service list
        if not specs and self.services:
            for svc in self.services:
                specs[svc] = ServiceSpec(name=svc)

        logger.info("Decomposed into %d service(s): %s", len(specs), list(specs.keys()))
        return specs

    # ------------------------------------------------------------------
    # Phase 2: Create service instances
    # ------------------------------------------------------------------

    def _create_instance(self, service_name: str, spec: ServiceSpec) -> ServiceInstance:
        """Create a ServiceInstance with port assignment and env vars."""
        port = self._BASE_PORT + len(self.instances)
        session_id = f"meta-{service_name}-{uuid.uuid4().hex[:8]}"

        # Determine dependencies from apis_consumed
        dependencies: list[str] = []
        for api in spec.apis_consumed:
            # Match consumed APIs to other services that expose them
            for other_name, other_inst in self.instances.items():
                if other_name != service_name and any(
                    api in exposed for exposed in other_inst.spec.apis_exposed
                ):
                    dependencies.append(other_name)

        env_vars = {
            "SERVICE_NAME": service_name,
            "PORT": str(port),
            "NODE_ENV": "production",
        }
        # Add env pointers to dependent services
        for dep in dependencies:
            dep_inst = self.instances.get(dep)
            if dep_inst:
                env_key = f"{dep.upper()}_URL"
                env_vars[env_key] = f"http://{dep}:{dep_inst.port}"

        return ServiceInstance(
            name=service_name,
            spec=spec,
            session_id=session_id,
            port=port,
            env_vars=env_vars,
            dependencies=dependencies,
        )

    # ------------------------------------------------------------------
    # Phase 3: Contract coordination
    # ------------------------------------------------------------------

    async def _coordinate_contracts(self) -> dict:
        """Ensure type-safe contracts between services."""
        if len(self.instances) < 2:
            return {"contracts": {}, "shared_types": ""}

        # Build a summary of all service APIs for the planning agent
        service_summaries = []
        for name, inst in self.instances.items():
            service_summaries.append(
                f"- {name} ({inst.spec.stack}): exposes {inst.spec.apis_exposed}, "
                f"consumes {inst.spec.apis_consumed}"
            )

        result = await run_planning_agent(
            "vp_engineering",
            AGENTS["vp_engineering"],
            f"""Define inter-service API contracts for these services:

{chr(10).join(service_summaries)}

For each service-to-service dependency, define:
1. Endpoint path and HTTP method
2. Request schema (JSON)
3. Response schema (JSON)
4. Error responses

Also generate shared type definitions that both producer and consumer can use.

Output as JSON:
{{
    "contracts": {{
        "api->frontend": [{{"endpoint": "/api/items", "method": "GET", "request": {{}}, "response": {{}}}}]
    }},
    "shared_types": "// TypeScript interfaces or Python models"
}}""",
        )

        try:
            raw = result.output
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse contracts: %s", exc)

        return {"contracts": {}, "shared_types": ""}

    # ------------------------------------------------------------------
    # Phase 4: Build services via LangGraph (parallel)
    # ------------------------------------------------------------------

    async def _build_services(self, directive: str) -> list[dict]:
        """Run a Nexus graph for each service in parallel."""

        async def _build_one(name: str, instance: ServiceInstance) -> dict:
            service_directive = (
                f"Build the '{name}' service for: {directive}\n"
                f"Responsibility: {instance.spec.responsibility}\n"
                f"Stack: {instance.spec.stack}\n"
                f"Data owned: {instance.spec.data_owned}\n"
                f"APIs exposed: {instance.spec.apis_exposed}\n"
                f"APIs consumed: {instance.spec.apis_consumed}"
            )
            service_path = os.path.join(self._project_path, name)
            os.makedirs(service_path, exist_ok=True)

            try:
                nexus_app = compile_nexus_dynamic()
                initial_state = NexusState(
                    directive=service_directive,
                    source="api",
                    session_id=instance.session_id,
                    project_path=service_path,
                )
                config = {"configurable": {"thread_id": instance.session_id}}
                result = await nexus_app.ainvoke(initial_state.model_dump(), config=config)
                instance.result = {
                    "status": "complete",
                    "demo_summary": result.get("demo_summary", ""),
                    "cost": result.get("cost", {}),
                }
                return instance.result
            except Exception as exc:
                logger.error("Service '%s' build failed: %s", name, exc, exc_info=True)
                instance.result = {"status": "error", "error": str(exc)}
                return instance.result

        coros = [_build_one(name, inst) for name, inst in self.instances.items()]
        results = await asyncio.gather(*coros, return_exceptions=True)

        final: list[dict] = []
        for i, res in enumerate(results):
            if isinstance(res, BaseException):
                svc_name = list(self.instances.keys())[i]
                self.instances[svc_name].result = {"status": "error", "error": str(res)}
                final.append(self.instances[svc_name].result)  # type: ignore[arg-type]
            else:
                final.append(res)  # type: ignore[arg-type]
        return final

    # ------------------------------------------------------------------
    # Phase 5: Docker Compose generation
    # ------------------------------------------------------------------

    def _generate_docker_compose(self) -> str:
        """Generate docker-compose.yml for all services."""
        compose: dict = {
            "version": "3.8",
            "services": {},
        }

        for service_name, instance in self.instances.items():
            compose["services"][service_name] = {
                "build": f"./{service_name}",
                "ports": [f"{instance.port}:{instance.port}"],
                "environment": instance.env_vars,
                "depends_on": instance.dependencies,
            }

        return yaml.dump(compose, default_flow_style=False, sort_keys=False)

    # ------------------------------------------------------------------
    # Phase 6: Integration tests
    # ------------------------------------------------------------------

    async def _run_integration_tests(self) -> dict:
        """Run integration tests across all services."""
        if len(self.instances) < 2:
            return {"status": "skipped", "reason": "single service, no integration needed"}

        service_summaries = []
        for name, inst in self.instances.items():
            status = inst.result.get("status", "unknown") if inst.result else "unknown"
            service_summaries.append(f"- {name}: {status} (port {inst.port})")

        result = await run_planning_agent(
            "tech_lead",
            AGENTS["tech_lead"],
            f"""Plan integration tests for these services:

{chr(10).join(service_summaries)}

Define:
1. Service health check tests (each service responds on its port)
2. Contract compliance tests (API requests/responses match contracts)
3. End-to-end flow tests (a request through the full service chain)
4. Failure mode tests (what happens when one service is down)

Output a test plan as JSON:
{{
    "health_checks": [...],
    "contract_tests": [...],
    "e2e_tests": [...],
    "failure_tests": [...]
}}""",
        )

        try:
            raw = result.output
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return {"status": "planned", "plan": json.loads(raw[start:end])}
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

        return {"status": "planned", "plan": result.output[:1000]}
