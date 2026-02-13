"""SSoT service for directive lifecycle data."""

from dataclasses import dataclass, field

from src.memory.store import memory


@dataclass
class DirectiveStatus:
    directive_id: str
    text: str = ""
    status: str = ""
    intent: str = ""
    project_path: str = ""
    tasks: list[dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class DirectiveService:
    """Unified access to directive lifecycle."""

    def get_directive(self, directive_id: str) -> DirectiveStatus | None:
        """Get directive with all related tasks."""
        directive = memory.get_directive(directive_id)
        if not directive:
            return None

        status = DirectiveStatus(
            directive_id=directive_id,
            text=directive.get("text", ""),
            status=directive.get("status", ""),
            intent=directive.get("intent", ""),
            project_path=directive.get("project_path", ""),
            created_at=directive.get("created_at", ""),
            updated_at=directive.get("updated_at", ""),
        )

        # Get related tasks from task_board
        try:
            tasks = memory.get_board_tasks(directive_id)
            status.tasks = tasks if tasks else []
        except Exception:
            pass

        return status

    def list_active_directives(self) -> list[DirectiveStatus]:
        """Get all active directives."""
        # Query for directives not in terminal states
        try:
            # There's no get_active_directives method, so we query the db directly
            # via get_active_directive which returns the most recent non-complete directive
            directive = memory.get_active_directive()
            if directive:
                return [DirectiveStatus(
                    directive_id=directive.get("id", ""),
                    text=directive.get("text", ""),
                    status=directive.get("status", ""),
                    intent=directive.get("intent", ""),
                    project_path=directive.get("project_path", ""),
                    created_at=directive.get("created_at", ""),
                    updated_at=directive.get("updated_at", ""),
                )]
            return []
        except Exception:
            return []


directive_service = DirectiveService()
