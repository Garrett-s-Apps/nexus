"""
NEXUS Org Chart Generator

Auto-generates ORG_CHART.md from the current live agent registry.
Called after every org change so the org chart always reflects reality.
"""

import os
import time

from src.agents.registry import registry


def generate_org_chart(output_path: str | None = None) -> str:
    """Generate a full org chart markdown document from the live registry."""

    agents = registry.get_active_agents()
    if not agents:
        return "# NEXUS Organization Chart\n\nNo agents currently active."

    agent_map = {a.id: a for a in agents}
    layers: dict[str, list] = {}
    for a in agents:
        layers.setdefault(a.layer, []).append(a)

    reporting_tree = registry.get_reporting_tree("ceo")

    model_counts: dict[str, int] = {}
    for a in agents:
        key = f"{a.provider}/{a.model}"
        model_counts[key] = model_counts.get(key, 0) + 1

    layer_counts: dict[str, int] = {}
    for a in agents:
        layer_counts[a.layer] = layer_counts.get(a.layer, 0) + 1

    changelog = registry.get_changelog(10)

    doc = f"""# NEXUS Organization Chart

_Auto-generated from live registry at {time.strftime('%Y-%m-%d %H:%M:%S')}_

## Reporting Structure

```
GARRETT (Human CEO)
  Sets direction, reviews demos, gives feedback
  │
{_indent_tree(reporting_tree)}```

## Agents by Layer

"""

    for layer_name in ["executive", "management", "senior", "implementation", "quality", "consultant"]:
        if layer_name in layers:
            doc += f"### {layer_name.title()} Layer\n\n"
            doc += "| Agent | ID | Model | Reports To | Status |\n"
            doc += "|-------|----|-------|------------|--------|\n"
            for a in layers[layer_name]:
                reports_name = agent_map[a.reports_to].name if a.reports_to and a.reports_to in agent_map else "Garrett"
                status = a.status
                if a.status == "temporary":
                    if a.temp_expiry:
                        remaining = (a.temp_expiry - time.time()) / 3600
                        status = f"temp ({remaining:.0f}h remaining)"
                    else:
                        status = "temporary"
                doc += f"| {a.name} | `{a.id}` | {a.provider}/{a.model} | {reports_name} | {status} |\n"
            doc += "\n"

    doc += f"""## Summary

| Metric | Value |
|--------|-------|
| Total Active Agents | {len(agents)} |
| Executive Layer | {layer_counts.get('executive', 0)} |
| Management Layer | {layer_counts.get('management', 0)} |
| Senior Layer | {layer_counts.get('senior', 0)} |
| Implementation Layer | {layer_counts.get('implementation', 0)} |
| Quality Layer | {layer_counts.get('quality', 0)} |
| Consultant Layer | {layer_counts.get('consultant', 0)} |

## Model Distribution

| Provider/Model | Agent Count |
|---------------|-------------|
"""

    for model_key, count in sorted(model_counts.items()):
        doc += f"| {model_key} | {count} |\n"

    if changelog:
        doc += "\n## Recent Org Changes\n\n"
        doc += "| Time | Action | Agent | Details |\n"
        doc += "|------|--------|-------|--------|\n"
        for entry in changelog:
            ts = time.strftime('%Y-%m-%d %H:%M', time.localtime(entry['timestamp']))
            doc += f"| {ts} | {entry['action']} | {entry.get('agent_id', '-')} | {entry.get('details', '')[:80]} |\n"

    if output_path:
        with open(output_path, "w") as f:
            f.write(doc)

    return doc


def _indent_tree(tree: str) -> str:
    lines = tree.strip().split("\n")
    return "\n".join(f"  {line}" for line in lines) + "\n"


def update_org_chart_in_repo(project_path: str):
    """Update ORG_CHART.md in the repo root after an org change."""
    chart_path = os.path.join(project_path, "ORG_CHART.md")
    generate_org_chart(chart_path)
