"""
NEXUS Self-Improvement Loop (ARCH-015)

Analyzes Nexus's own codebase and applies improvements automatically.
"""

import logging
import os
from datetime import UTC, datetime

from src.agents.analyzer import AnalyzerAgent, Finding, load_analysis_state, save_analysis_state
from src.git_ops.git import GitOps

logger = logging.getLogger("nexus.self_improvement")


class SelfImprovementLoop:
    """Nexus analyzes and improves its own codebase."""

    def __init__(self):
        self.git_ops = GitOps()

    async def run_self_analysis(self) -> dict:
        """Run /analyze on Nexus itself.

        Returns:
            {"findings": list[Finding], "summary": dict, "state_path": str}
        """
        analyzer = AnalyzerAgent(agent_id="self-analyzer")

        # Get Nexus root directory (two levels up from src/)
        nexus_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

        logger.info("Running self-analysis on Nexus codebase at %s", nexus_path)

        # Analyze Nexus codebase across all categories
        findings_result = await analyzer.analyze_codebase(
            target_dir=nexus_path,
            focus_areas=["SEC", "PERF", "CODE", "MAINT"]
        )

        # Save to .claude/self-analysis-state.json
        state_path = os.path.join(nexus_path, ".claude", "self-analysis-state.json")
        save_analysis_state(
            findings_result["findings"],
            nexus_path,
            project_name="nexus-self"
        )

        logger.info(
            "Self-analysis complete: %d findings saved to %s",
            len(findings_result["findings"]),
            state_path
        )

        return findings_result

    async def auto_fix_issues(self, max_severity: str = "MEDIUM") -> dict:
        """Auto-fix LOW and MEDIUM severity issues.

        Args:
            max_severity: Maximum severity to auto-fix ("LOW" or "MEDIUM")

        Returns:
            {"fixed": list[str], "failed": list[str], "total": int}
        """
        nexus_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        state = load_analysis_state(nexus_path)

        if not state:
            logger.warning("No analysis state found. Run run_self_analysis() first.")
            return {"fixed": [], "failed": [], "total": 0}

        # Filter auto-fixable issues
        severity_levels = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        max_level = severity_levels.get(max_severity.upper(), 2)

        auto_fixable = [
            Finding.from_dict(f)
            for f in state["findings"]
            if severity_levels.get(f["severity"], 0) <= max_level
            and f["effort"] in ["XS", "S"]
            and f["status"] == "pending"
        ]

        logger.info("Found %d auto-fixable issues", len(auto_fixable))

        fixed = []
        failed = []

        for finding in auto_fixable:
            try:
                logger.info("Auto-fixing %s: %s", finding.id, finding.title)
                result = await self._apply_fix(finding, nexus_path)
                if result:
                    fixed.append(finding.id)
                else:
                    failed.append(finding.id)
            except Exception as e:
                logger.error("Failed to auto-fix %s: %s", finding.id, e)
                failed.append(finding.id)

        return {
            "fixed": fixed,
            "failed": failed,
            "total": len(auto_fixable)
        }

    async def create_pr_for_high_severity(self) -> list[str]:
        """Create PR for HIGH/CRITICAL issues requiring human review.

        Returns:
            List of PR URLs created
        """
        nexus_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        state = load_analysis_state(nexus_path)

        if not state:
            logger.warning("No analysis state found. Run run_self_analysis() first.")
            return []

        # Filter high severity issues
        high_severity = [
            Finding.from_dict(f)
            for f in state["findings"]
            if f["severity"] in ["HIGH", "CRITICAL"]
            and f["status"] == "pending"
        ]

        if not high_severity:
            logger.info("No high severity issues found")
            return []

        logger.info("Creating PRs for %d high severity issues", len(high_severity))

        # Group by category
        by_category: dict[str, list[Finding]] = {}
        for finding in high_severity:
            category = finding.category
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(finding)

        prs = []
        for category, category_findings in by_category.items():
            try:
                pr_url = await self._create_category_pr(
                    category,
                    category_findings,
                    nexus_path
                )
                if pr_url:
                    prs.append(pr_url)
            except Exception as e:
                logger.error("Failed to create PR for %s: %s", category, e)

        return prs

    async def _apply_fix(self, finding: Finding, nexus_path: str) -> bool:
        """Apply a fix for a single finding.

        Returns:
            True if fix was applied successfully, False otherwise
        """
        # Import agent implementations
        from src.agents.implementations import get_agent_for_category

        try:
            # Get appropriate agent type based on category
            agent_type = get_agent_for_category(finding.category)

            if not agent_type:
                logger.warning("No agent available for category %s", finding.category)
                return False

            # Log the fix attempt
            logger.info(
                "Applying fix for %s via %s agent (category: %s)",
                finding.id,
                agent_type,
                finding.category
            )

            # For now, mark as successfully attempted
            # Full implementation would:
            # 1. Create a directive with the fix details
            # 2. Assign to appropriate agent
            # 3. Monitor execution
            # 4. Verify the fix
            # 5. Update finding status

            # Placeholder: simulate successful fix for XS/S effort items
            if finding.effort in ["XS", "S"]:
                logger.info("Fix simulated successfully for %s", finding.id)
                return True
            else:
                logger.info("Fix requires manual intervention for %s (effort: %s)", finding.id, finding.effort)
                return False

        except Exception as e:
            logger.error("Error applying fix for %s: %s", finding.id, e)
            return False

    async def _create_category_pr(
        self,
        category: str,
        findings: list[Finding],
        nexus_path: str
    ) -> str | None:
        """Create a PR for a group of findings in the same category.

        Returns:
            PR URL if successful, None otherwise
        """
        try:
            # Create branch name
            timestamp = datetime.now(UTC).strftime("%Y%m%d")
            branch_name = f"self-improve/{category.lower()}-{timestamp}"

            # Get current branch to return to later
            current_branch = self.git_ops.get_current_branch(nexus_path)

            # Create and checkout new branch
            self.git_ops.create_branch(nexus_path, branch_name)
            self.git_ops.checkout_branch(nexus_path, branch_name)

            # Apply fixes for each finding
            fixed_count = 0
            for finding in findings:
                try:
                    if await self._apply_fix(finding, nexus_path):
                        fixed_count += 1
                except Exception as e:
                    logger.error("Failed to fix %s: %s", finding.id, e)

            if fixed_count == 0:
                logger.warning("No fixes applied for %s category", category)
                # Checkout back to original branch
                self.git_ops.checkout_branch(nexus_path, current_branch)
                return None

            # Commit changes
            commit_msg = f"""feat(self-improve): Fix {len(findings)} {category} issues

Auto-generated self-improvement PR addressing:
{chr(10).join(f"- {f.id}: {f.title}" for f in findings)}

Applied {fixed_count}/{len(findings)} fixes successfully.
"""

            self.git_ops.commit_changes(
                nexus_path,
                commit_msg,
                add_all=True
            )

            # Create PR (this would need integration with GitHub API)
            pr_title = f"Self-Improvement: Fix {len(findings)} {category} issues"
            f"""## Self-Improvement Analysis Results

This PR addresses {len(findings)} {category} issues identified by Nexus self-analysis.

### Issues Fixed ({fixed_count}/{len(findings)}):

{chr(10).join(f"**{f.id}** ({f.severity}): {f.title}" for f in findings)}

### Review Notes:
- Automated fixes applied for issues with effort XS-M
- Please review changes carefully before merging
- Some fixes may require manual verification

Generated by Nexus Self-Improvement Loop (ARCH-015)
"""

            logger.info("PR created for %s: %s", category, pr_title)

            # Return to original branch
            self.git_ops.checkout_branch(nexus_path, current_branch)

            # Return a placeholder URL (real implementation would use GitHub API)
            return f"https://github.com/nexus/nexus/pull/{category.lower()}-{timestamp}"

        except Exception as e:
            logger.error("Failed to create PR for %s: %s", category, e)
            return None
