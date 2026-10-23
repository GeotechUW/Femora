"""Terminal dashboard; all remote operations go through tracked job handles."""

from pathlib import Path
from dataclasses import replace
import json

from requests.exceptions import RequestException

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static, TextArea

from .tracking import JobRecord, JobRegistry, connect, sync, _CONNECTORS


class Prompt(ModalScreen):
    BINDINGS = [("escape", "dismiss(None)", "Back")]

    def __init__(self, text, value=""):
        super().__init__()
        self.text, self.value = text, value

    def compose(self):
        with Vertical(id="dialog"):
            yield Static(self.text, markup=False)
            yield Input(value=self.value, id="answer")
            yield Button("Continue", id="continue", variant="primary")

    def on_mount(self):
        self.query_one(Input).focus()

    def on_input_submitted(self, event):
        self.dismiss(event.value)

    def on_button_pressed(self, event):
        self.dismiss(self.query_one(Input).value)


class Details(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Back")]

    def __init__(self, text):
        super().__init__()
        self.text = text

    def compose(self):
        with Vertical(id="details-dialog"):
            yield TextArea(self.text, read_only=True, id="details-text")
            yield Button("Back", id="back")

    def on_mount(self):
        self.query_one(TextArea).focus()

    def on_button_pressed(self, event):
        self.dismiss()


class JobTracker(App):
    TITLE = "Femora Jobs"
    CSS = """
    DataTable { height: 1fr; }
    #notice { height: 3; padding: 0 1; }
    ModalScreen { align: center middle; background: $background 70%; }
    #dialog { width: 85%; height: auto; max-height: 85%; overflow-y: auto;
              padding: 1 2; border: round $accent; background: $surface; }
    #details-dialog { width: 85%; height: 85%; padding: 1 2;
                      border: round $accent; background: $surface; }
    #details-text { height: 1fr; }
    """
    BINDINGS = [("q", "quit", "Quit"), ("l", "login", "Login"),
                ("r", "refresh_jobs", "Refresh"), ("d", "download", "Download"),
                ("c", "cancel_job", "Cancel"), ("h", "hide_job", "Hide local"),
                ("x", "cleanup_job", "Clean remote")]

    def __init__(self, registry=None, poll_interval=30, tenant="https://designsafe.tapis.io", app_id=None):
        super().__init__()
        self.registry = registry or JobRegistry()
        self.connections = {}
        self.records = []
        self.busy = False
        self.poll_interval = poll_interval
        self.tenant, self.app_id = tenant, app_id

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row", zebra_stripes=True)
        yield Static("Cached records. L: login and discover remote jobs (also works with an empty list). Enter: details.",
                     id="notice", markup=False)
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns("Workflow", "Platform", "Status (cached)",
                                             "Submitted UTC", "Checked UTC", "Job ID")
        self.reload_rows()
        self.set_interval(self.poll_interval, self.poll)

    def reload_rows(self):
        table = self.query_one(DataTable)
        row = table.cursor_row
        selected_key = self.records[row].key if self.records and row < len(self.records) else None
        self.records = self.registry.list()
        table.clear()
        for record in self.records:
            table.add_row(record.name, record.platform, record.state, record.submitted_at,
                          record.checked_at or "never", record.id, key=record.key)
        if self.records:
            new_row = next((i for i, r in enumerate(self.records) if r.key == selected_key),
                           min(row, len(self.records) - 1))
            table.move_cursor(row=new_row)
        table.focus()

    def selected(self):
        table = self.query_one(DataTable)
        return self.records[table.cursor_row] if self.records else None

    @staticmethod
    def connection_key(record):
        return record.platform, record.connection.get("base_url"), record.connection.get("username")

    def notice(self, text):
        self.query_one("#notice", Static).update(text)

    def show_download_progress(self, phase, count, total):
        if phase == "validating":
            self.notice("Download received. Validating ZIP...")
            return
        label = "Receiving" if phase == "receiving" else "Saving"
        amount = f"{count / (1024 * 1024):.1f} MiB"
        if total:
            percent = min(100, 100 * count / total)
            self.notice(f"{label}: {amount} / {total / (1024 * 1024):.1f} MiB ({percent:.0f}%)")
        else:
            self.notice(f"{label}: {amount} (total size not provided by server)")

    def action_login(self):
        record = self.selected()
        if self.busy:
            return
        if record is None:
            record = JobRecord("", "", "tacc", "", "", {
                "base_url": self.tenant, "app_id": self.app_id or "job-tracking",
            }, {})
        elif self.app_id:
            record = replace(record, connection={**record.connection, "app_id": self.app_id})
        try:
            # Private console login happens outside the alternate-screen UI.
            with self.suspend():
                target = _CONNECTORS[record.platform](record)
            metadata = target.tracking_metadata()
            connection = metadata["connection"]
            account = (metadata["platform"], connection.get("base_url"), connection.get("username"))
            self.connections[account] = target
            self.connections[self.connection_key(record)] = target
            self.notice("Connected. Discovering remote Femora jobs; credentials remain in memory.")
            self.action_refresh_jobs()
        except (Exception, KeyboardInterrupt) as error:
            self.notice(f"Login did not complete ({type(error).__name__}); no jobs submitted.")

    def poll(self):
        if self.connections and not self.busy and len(self.screen_stack) == 1:
            self.action_refresh_jobs()

    def action_refresh_jobs(self):
        if self.busy:
            return
        if not self.connections:
            self.reload_rows()
            self.notice("Local cache reloaded. Press L to login and discover remote jobs.")
            return
        self.busy = True
        self.remote("refresh", [])

    def on_data_table_row_selected(self, event):
        record = self.selected()
        if not record or self.busy:
            return
        if self.connection_key(record) in self.connections:
            self.busy = True
            self.remote("details", [record])
        else:
            self.show_details(record, {})

    def show_details(self, record, details):
        self.push_screen(Details(
            f"{record.name}\nJob: {record.id}\nPlatform: {record.platform}\n"
            f"Cached status: {record.state} ({record.native_state})\n"
            f"Last checked: {record.checked_at or 'never'}\n\n"
            + json.dumps({"resources": record.resources, "connection": record.connection,
                          "remote": details}, indent=2, default=str)))

    def action_download(self):
        record = self.selected()
        if not self.ready(record):
            return
        self.push_screen(Prompt("Download ZIP destination (existing files will not be overwritten):",
                                str(Path("example_outputs") / f"{record.id}.zip")),
                         lambda value: self.start("download", record, value) if value else None)

    def action_cancel_job(self):
        record = self.selected()
        if not self.ready(record):
            return
        self.push_screen(Prompt(f"This may stop running work. Type the full UUID to cancel:\n{record.id}"),
                         lambda value: self.start("cancel", record) if value == record.id else
                         self.notice("Cancellation not requested."))

    def action_hide_job(self):
        record = self.selected()
        if not record or self.busy:
            return
        self.push_screen(Prompt(f"Remove this job from the local tracker only?\n"
                                f"My Data and scratch files will not be deleted.\n"
                                f"Type the full UUID to confirm:\n{record.id}"),
                         lambda value: self.hide_job(record) if value == record.id else
                         self.notice("Job was not removed from the tracker."))

    def hide_job(self, record):
        if self.registry.hide(record.key):
            self.reload_rows()
            self.notice("Job hidden locally. Remote job and files are unchanged.")

    def action_cleanup_job(self):
        record = self.selected()
        if self.ready(record):
            self.start("cleanup_preview", record)

    def show_cleanup_prompt(self, record, plan):
        scratch = plan.scratch[1] if plan.scratch else "(not reported; skipped)"
        archive = plan.archive[1] if plan.archive else "(not reported; skipped)"
        self.push_screen(Prompt(
            f"Delete this finished job's output folders and hide it in Tapis?\n"
            f"Stampede3 scratch: {scratch}\nDesignSafe My Data: {archive}\n"
            f"This cannot be undone. Type DELETE {record.id} to confirm:"),
            lambda value: self.start("cleanup", record, plan)
            if value == f"DELETE {record.id}" else self.notice("Remote cleanup cancelled."))

    def ready(self, record):
        if not record or self.busy:
            return False
        if self.connection_key(record) not in self.connections:
            self.notice("Press L to login first.")
            return False
        return True

    def start(self, operation, record, value=None):
        if self.busy:
            return
        self.busy = True
        self.remote(operation, [record], value)

    @work(thread=True)
    def remote(self, operation, records, value=None):
        try:
            if operation == "refresh":
                discovered = set()
                # The same adapter may also be stored under an older cache key.
                for target in {id(t): t for t in self.connections.values()}.values():
                    for record in sync(target, registry=self.registry):
                        discovered.add(record.key)
                records = [r for r in self.registry.list()
                           if self.connection_key(r) in self.connections and r.key not in discovered]
            for record in records:
                job = connect(record.key, platform=self.connections[self.connection_key(record)],
                              registry=self.registry)
                if operation == "refresh":
                    job.status()
                elif operation == "details":
                    details = job.details()
                    self.call_from_thread(self.show_details, job.record, details)
                elif operation == "download":
                    self.call_from_thread(self.notice, "Connecting to Tapis for download...")
                    job.download(value, progress=lambda phase, count, total:
                                 self.call_from_thread(self.show_download_progress, phase, count, total))
                    self.call_from_thread(self.notice, f"Download complete: {value}")
                    return
                elif operation == "cancel":
                    if job.status().state not in {"succeeded", "failed", "cancelled"}:
                        job.cancel()
                        self.call_from_thread(self.notice, "Cancellation requested, not confirmed. Refresh to verify.")
                        return
                elif operation == "cleanup_preview":
                    plan = job.cleanup_plan()
                    self.call_from_thread(self.show_cleanup_prompt, record, plan)
                    return
                elif operation == "cleanup":
                    job.cleanup(value)
                    self.registry.hide(record.key)
                    self.call_from_thread(self.notice, "Remote output cleanup completed; job hidden in Tapis and locally.")
                    return
            self.call_from_thread(self.notice, f"{operation.capitalize()} completed. Statuses show their last check time.")
        except Exception as error:
            if operation == "download":
                if isinstance(error, FileExistsError):
                    message = "Download not started: ZIP or .part already exists. Choose a new destination."
                elif isinstance(error, RequestException):
                    status = getattr(getattr(error, "response", None), "status_code", None)
                    detail = f"HTTP {status}" if status else type(error).__name__
                    message = f"Download transfer failed ({detail}). A .part file may remain; choose a new destination."
                elif isinstance(error, OSError):
                    message = f"Download failed while writing locally ({type(error).__name__}, errno={error.errno}). " \
                              "Check free space and destination permissions; a .part file may remain."
                else:
                    message = f"Download failed ({type(error).__name__}). A .part file may remain."
                self.call_from_thread(self.notice, message)
            elif operation == "cleanup_preview":
                reason = str(error) if isinstance(error, ValueError) else type(error).__name__
                self.call_from_thread(self.notice, f"Cleanup unavailable: {reason}. No files changed.")
            elif operation == "cleanup":
                self.call_from_thread(self.notice, f"Cleanup stopped ({type(error).__name__}). "
                                      "Some files may already be removed; inspect the job before retrying.")
            else:
                self.call_from_thread(self.notice, f"{operation.capitalize()} failed ({type(error).__name__}); "
                                      "private details omitted. No automatic retry or resubmission.")
        finally:
            if operation != "cleanup_preview":
                self.call_from_thread(self.reload_rows)
            self.busy = False
