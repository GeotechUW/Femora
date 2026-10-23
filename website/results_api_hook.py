"""Style curated API navigation without duplicating generated reference pages."""

GROUP_ICONS = {
    "core": "material/cog-outline",
    "model": "material/cube-outline",
    "materials": "material/layers-outline",
    "sections": "material/vector-square",
    "transformations": "material/rotate-3d-variant",
    "elements": "material/vector-line",
    "damping": "material/waveform",
    "regions": "material/vector-selection",
    "mesh parts": "material/grid",
    "assembly": "material/puzzle-outline",
    "interfaces": "material/connection",
    "constraints": "material/lock-outline",
    "mass": "material/weight",
    "selections": "material/selection",
    "time series": "material/chart-timeline-variant",
    "ground motions": "material/waveform",
    "loads": "material/arrow-down-bold-outline",
    "patterns": "material/chart-line",
    "recorders": "material/content-save-outline",
    "actions": "material/gesture-tap-button",
    "analysis": "material/calculator-variant-outline",
    "process": "material/format-list-numbered",
    "extension API": "material/puzzle-outline",
    "algorithm": "material/function-variant",
    "constraint handlers": "material/lock-outline",
    "convergence tests": "material/check-circle-outline",
    "integrator": "material/chart-timeline-variant",
    "system": "material/server-outline",
    "numberer": "material/format-list-numbered",
    "Results & Postprocessing": "material/chart-line",
    "Overview": "material/book-open-outline",
    "Reading Results": "material/folder-open-outline",
    "Building Responses": "material/office-building-outline",
    "Visualization": "material/movie-open-outline",
    "Advanced": "material/tune",
    "File Readers": "material/file-table-outline",
    "Reader Extensions": "material/puzzle-outline",
    "Errors": "material/alert-circle-outline",
    "jobs": "material/sitemap-outline",
    "workflows": "material/source-branch",
    "tasks": "material/format-list-checks",
    "execute workflows": "material/play-circle-outline",
    "allocation backends": "material/server-network",
    "submit remotely": "material/cloud-upload-outline",
    "resource validation": "material/clipboard-check-outline",
    "track jobs": "material/radar",
    "bundles and replay": "material/package-variant-closed",
    "command line": "material/console",
    "platform interfaces": "material/puzzle-outline",
    "tracking registry": "material/database-outline",
    "runtime": "material/cog-play-outline",
}
GROUP_ICONS = {title.lower(): icon for title, icon in GROUP_ICONS.items()}
FUNCTION_LABELS = {"open result files", "register a reader", "run workflows",
                   "submit workflows", "discover and reconnect"}
CLASS_ICONS = {
    "Workflow": "material/source-branch",
    "Python": "material/language-python",
    "Command": "material/console-line",
    "OpenSees": "material/play-box-outline",
    "TaskContext": "material/folder-information-outline",
    "RunResult": "material/check-circle-outline",
    "ProcessResult": "material/text-box-check-outline",
    "TACC": "material/server-network",
    "TACCPlatform": "material/cloud-outline",
    "TACCSettings": "material/tune",
    "TACCValidator": "material/clipboard-check-outline",
    "ValidationReport": "material/clipboard-text-outline",
    "ValidationIssue": "material/alert-outline",
    "QueueLimits": "material/speedometer",
    "TrackedJob": "material/radar",
    "TACCJob": "material/cloud-check-outline",
    "JobStatus": "material/progress-clock",
    "JobRecord": "material/card-text-outline",
    "JobSummary": "material/text-box-outline",
    "JobRegistry": "material/database-outline",
    "JobCleanupPlan": "material/delete-outline",
    "RuntimeInfo": "material/information-outline",
}


def on_page_context(context, **kwargs):
    """Style curated navigation, preserving the spelling of public class names."""
    def visit(items, in_results=False):
        for item in items:
            label = item.title.lower()
            selected = in_results or item.title in {"results & postprocessing", "Results & Postprocessing", "jobs", "runtime", "core"}
            if selected:
                if label in GROUP_ICONS or label in FUNCTION_LABELS:
                    item.title = label
                if not hasattr(item, "meta"):
                    item.meta = {}
                icon = GROUP_ICONS.get(label) or CLASS_ICONS.get(item.title)
                if icon is None and item.title.endswith("Error"):
                    icon = "material/alert-circle-outline"
                if icon is None:
                    icon = ("material/code-braces" if label in FUNCTION_LABELS
                            else "material/cube-outline")
                item.meta.setdefault("icon", icon)
            visit(getattr(item, "children", None) or [], selected)

    visit(context["nav"])
    return context
