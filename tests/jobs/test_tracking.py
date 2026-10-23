"""Registry and tracker tests use fake handles; never submit remote jobs."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from femora.jobs.tracking import JobRegistry, add, connect, list_jobs, record_submission, sync
from femora.jobs.platforms import JobStatus, JobSummary, TACCPlatform, TACCSettings


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("FEMORA_JOBS_DB", str(tmp_path / "jobs.db"))
    return JobRegistry()


def test_registry_persists_concurrent_jobs(store):
    with ThreadPoolExecutor(4) as pool:
        records = list(pool.map(lambda i: add(str(i), name=f"workflow-{i}", registry=store), range(12)))
    assert len(list_jobs(registry=JobRegistry(store.path))) == 12
    assert store.get(records[0].id) == records[0]
    assert add(records[0].id, registry=store) == records[0]


def test_secrets_not_saved_and_ambiguous_account(store):
    with pytest.raises(ValueError, match="no credentials"):
        add("id", connection={"password": "secret"}, registry=store)
    with pytest.raises(ValueError, match="without credentials"):
        add("id", connection={"base_url": "https://user:secret@example.com"}, registry=store)
    one = add("id", connection={"username": "one"}, resources={"nodes": 1, "token": "secret"}, registry=store)
    add("id", connection={"username": "two"}, registry=store)
    with pytest.raises(ValueError, match="ambiguous"):
        store.get("id")
    assert "secret" not in str(asdict(store.get(one.key)))


def test_cli_cached_list_and_import(store, monkeypatch, capsys):
    from femora.jobs.__main__ import main
    import sys
    monkeypatch.setattr(sys, "argv", ["jobs", "add", "old-id", "--name", "existing"])
    main()
    assert store.get("old-id").name == "existing"
    monkeypatch.setattr(sys, "argv", ["jobs", "list", "--json"])
    main()
    assert '"id": "old-id"' in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["jobs", "track"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit):
        main()


def test_reconnect_refresh_wait_and_cancel(store):
    record = add("job", registry=store)
    target = Mock()
    handle = target.job.return_value
    handle.status.return_value = JobStatus("succeeded", "FINISHED")
    job = connect(record.id, platform=target, registry=store)
    assert job.wait().state == "succeeded"
    assert store.get(record.key).checked_at
    assert store.get(record.key).state == "succeeded"
    job.cancel()
    assert store.get(record.key).state == "succeeded"  # cancellation request is not confirmation
    handle.cancel.assert_called_once()
    with pytest.raises(ValueError):
        job.wait(poll_interval=0)
    handle.status.return_value = JobStatus("running", "RUNNING")
    with pytest.raises(TimeoutError):
        job.wait(timeout=0)


def test_record_submission_whitelists_settings(store):
    target = Mock()
    target.tracking_metadata.return_value = {"platform": "tacc", "connection": {
        "username": "user", "base_url": "https://designsafe.tapis.io"}}
    record_submission(target, SimpleNamespace(id="new"),
                      TACCSettings("stampede3", "skx-dev", "PROJECT", 1, 48, 20), "study")
    assert store.get("new").resources["cores_per_node"] == 48
    assert store.get("new").name == "study"


def test_record_failure_never_changes_submit_outcome(monkeypatch):
    target = Mock()
    target.tracking_metadata.side_effect = OSError()
    with pytest.warns(UserWarning, match="do not resubmit"):
        record_submission(target, SimpleNamespace(id="already-submitted"), {}, "study")


def test_terminal_navigation_details_and_cancel_confirmation(store):
    from femora.jobs.tracker_ui import JobTracker, Details, Prompt
    from textual.widgets import DataTable, Input
    records = [add(str(i), name=f"case-{i}", registry=store) for i in range(2)]

    async def exercise():
        app = JobTracker(registry=store)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.query_one(DataTable).row_count == 2
            await pilot.press("down", "enter")
            assert isinstance(app.screen, Details)
            await pilot.press("escape")
            assert app.query_one(DataTable).cursor_row == 1
            target = Mock()
            app.connections[app.connection_key(app.selected())] = target
            app.start = Mock()
            await pilot.press("c")
            assert isinstance(app.screen, Prompt)
            app.screen.query_one(Input).value = "wrong"
            await pilot.press("enter")
            app.start.assert_not_called()
            await pilot.press("c")
            record = app.selected()
            app.screen.query_one(Input).value = record.id
            await pilot.press("enter")
            app.start.assert_called_once_with("cancel", record)
    asyncio.run(exercise())


def test_background_refresh_details_and_download(store, tmp_path):
    from femora.jobs.tracker_ui import JobTracker, Details
    record = add("job", registry=store)
    target = Mock()
    target.list_jobs.return_value = []
    target.tracking_metadata.return_value = {"platform": "tacc", "connection": {}}
    target.job.return_value.status.return_value = JobStatus("succeeded", "FINISHED")
    target.job.return_value.details.return_value = {"remoteJobId": "123"}

    async def exercise():
        app = JobTracker(registry=store)
        app.connections[app.connection_key(record)] = target
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("r")
            await app.workers.wait_for_complete()
            assert store.get("job").state == "succeeded"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, Details)
            await pilot.press("escape")
            app.start("download", record, str(tmp_path / "out.zip"))
            await app.workers.wait_for_complete()
            target.job.return_value.download.assert_called_once()
    asyncio.run(exercise())


def test_download_collision_reports_partial_file(store, tmp_path):
    from femora.jobs.tracker_ui import JobTracker
    from textual.widgets import Static
    record = add("job", registry=store)
    target = Mock()
    target.job.return_value.download.side_effect = FileExistsError("existing partial")

    async def exercise():
        app = JobTracker(registry=store)
        app.connections[app.connection_key(record)] = target
        async with app.run_test(size=(120, 40)):
            app.start("download", record, str(tmp_path / "job.zip"))
            await app.workers.wait_for_complete()
            assert "ZIP or .part already exists" in str(app.query_one("#notice", Static).render())
    asyncio.run(exercise())


def test_tracker_download_progress_with_and_without_total(store):
    from femora.jobs.tracker_ui import JobTracker
    from textual.widgets import Static

    async def exercise():
        app = JobTracker(registry=store)
        async with app.run_test(size=(120, 40)):
            notice = app.query_one("#notice", Static)
            app.show_download_progress("receiving", 1024 * 1024, 2 * 1024 * 1024)
            assert "50%" in str(notice.render())
            app.show_download_progress("receiving", 1024 * 1024, None)
            assert "1.0 MiB" in str(notice.render())
            assert "total size not provided" in str(notice.render())
            app.show_download_progress("validating", 1024 * 1024, None)
            assert "Validating ZIP" in str(notice.render())
    asyncio.run(exercise())


def test_tacc_discovery_paginates_filters_and_normalizes():
    client = Mock(base_url="https://designsafe.tapis.io", username="user")
    client.jobs.getJobList.side_effect = [
        [{"uuid": "unrelated", "owner": "user", "appId": "other", "name": "femora-fake"},
         {"uuid": "shared", "owner": "someone", "appId": "user-femora-workflow-stampede3"}],
        [SimpleNamespace(uuid="old", owner="user", appId="user-femora-workflow-stampede3",
                         appVersion="0.1", name="renamed", created="2026-01-01T00:00:00Z",
                         status="FINISHED", execSystemId="stampede3"),
         {"uuid": "custom", "owner": "user", "appId": "custom-app", "status": "QUEUED"}],
        [],
    ]
    target = TACCPlatform(client, app_id="custom-app", app_version="0.1",
                          storage_system="storage", input_directory="user/jobs")
    records = list(target.list_jobs(page_size=100))
    assert [r.id for r in records] == ["old", "custom"]
    assert records[0].name == "renamed" and records[0].status.state == "succeeded"
    assert records[1].status.state == "pending"
    assert [c.kwargs["skip"] for c in client.jobs.getJobList.call_args_list] == [0, 2, 4]
    assert all(c.kwargs["listType"] == "MY_JOBS" for c in client.jobs.getJobList.call_args_list)
    client.jobs.getJob.assert_not_called()
    client.jobs.submitJob.assert_not_called()
    client.files.mkdir.assert_not_called()


def test_tacc_discovery_repeated_page_fails_instead_of_looping():
    client = Mock(base_url="https://designsafe.tapis.io", username="user")
    client.jobs.getJobList.return_value = [{"uuid": "id", "owner": "user", "appId": "other"}]
    target = TACCPlatform(client, app_id="job-tracking", app_version="0.1",
                          storage_system="storage", input_directory="user/jobs")
    with pytest.raises(RuntimeError, match="did not advance"):
        list(target.list_jobs())
    assert client.jobs.getJobList.call_count == 2


def test_remote_discovery_rebuilds_empty_cache_and_updates_without_deleting(store):
    target = Mock()
    target.tracking_metadata.return_value = {"platform": "tacc", "connection": {
        "username": "user", "base_url": "https://designsafe.tapis.io", "app_id": "job-tracking"}}
    summary = JobSummary("remote", "old-study", "2026-01-01T00:00:00Z",
                         JobStatus("running", "RUNNING"),
                         connection={"app_id": "custom-app"},
                         resources={"system": "stampede3", "token": "secret"})
    target.list_jobs.return_value = [summary]
    first = list_jobs(platform=target, registry=store)[0]
    assert first.submitted_at == summary.submitted_at and first.checked_at
    assert first.connection["app_id"] == "custom-app"
    assert "secret" not in str(asdict(first))
    target.list_jobs.return_value = [JobSummary("remote", "renamed", summary.submitted_at,
                                               JobStatus("succeeded", "FINISHED"))]
    updated = sync(target, registry=store)[0]
    assert updated.state == "succeeded" and updated.name == "renamed"
    assert len(store.list()) == 1 and updated.resources["system"] == "stampede3"
    target.list_jobs.return_value = []
    assert sync(target, registry=store) == [] and len(store.list()) == 1
    target.list_jobs.side_effect = RuntimeError("offline")
    with pytest.raises(RuntimeError):
        sync(target, registry=store)
    assert store.get("remote").state == "succeeded"


def test_hidden_job_stays_hidden_after_remote_discovery(store):
    target = Mock()
    target.tracking_metadata.return_value = {"platform": "tacc", "connection": {
        "username": "user", "base_url": "https://designsafe.tapis.io"}}
    summary = JobSummary("remote", "study", "2026-01-01T00:00:00Z",
                         JobStatus("running", "RUNNING"))
    target.list_jobs.return_value = [summary]
    record = sync(target, registry=store)[0]
    assert store.hide(record.key)
    assert not store.hide(record.key)
    assert JobRegistry(store.path).list() == []
    assert sync(target, registry=JobRegistry(store.path)) == []
    assert store.list() == []
    with pytest.raises(ValueError, match="hidden"):
        add("remote", connection=record.connection, registry=store)
    target.job.assert_not_called()


def test_tracker_hide_confirmation_and_keyboard_details(store):
    from femora.jobs.tracker_ui import JobTracker, Details, Prompt
    from textual.widgets import DataTable, Input, TextArea
    record = add("job", registry=store)

    async def exercise():
        app = JobTracker(registry=store)
        async with app.run_test(size=(120, 40)) as pilot:
            app.show_details(record, {"lines": list(range(200))})
            await pilot.pause()
            assert isinstance(app.screen, Details)
            area = app.screen.query_one(TextArea)
            assert app.focused is area
            await pilot.press("pagedown")
            assert area.scroll_y > 0
            await pilot.press("escape")
            await pilot.press("h")
            assert isinstance(app.screen, Prompt)
            app.screen.query_one(Input).value = "wrong"
            await pilot.press("enter")
            assert app.query_one(DataTable).row_count == 1
            await pilot.press("h")
            app.screen.query_one(Input).value = record.id
            await pilot.press("enter")
            assert app.query_one(DataTable).row_count == 0
            assert store.is_hidden(record.key)
    asyncio.run(exercise())


def test_tracker_remote_cleanup_requires_confirmation(store):
    from femora.jobs.platforms.tacc_remote import JobCleanupPlan
    from femora.jobs.tracker_ui import JobTracker, Prompt
    from textual.widgets import DataTable, Input
    record = add("94a706b0-0306-4cbb-88ca-17e9d18b2a91-007", registry=store)
    target = Mock()
    plan = JobCleanupPlan(record.id, ("stampede3", f"/scratch/08189/user/tapis/{record.id}"), None)
    target.job.return_value.cleanup_plan.return_value = plan

    async def exercise():
        app = JobTracker(registry=store)
        app.connections[app.connection_key(record)] = target
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("x")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, Prompt)
            assert plan.scratch[1] in app.screen.text
            app.screen.query_one(Input).value = record.id
            await pilot.press("enter")
            target.job.return_value.cleanup.assert_not_called()
            assert app.query_one(DataTable).row_count == 1

            await pilot.press("x")
            await app.workers.wait_for_complete()
            await pilot.pause()
            app.screen.query_one(Input).value = f"DELETE {record.id}"
            await pilot.press("enter")
            await app.workers.wait_for_complete()
            await pilot.pause()
            target.job.return_value.cleanup.assert_called_once_with(plan)
            assert app.query_one(DataTable).row_count == 0
            assert store.is_hidden(record.key)
    asyncio.run(exercise())


def test_empty_tracker_login_discovers_remote_jobs(store, monkeypatch):
    from contextlib import nullcontext
    from femora.jobs.tracker_ui import JobTracker
    from femora.jobs import tracking
    from textual.widgets import DataTable
    target = Mock()
    target.tracking_metadata.return_value = {"platform": "tacc", "connection": {
        "username": "user", "base_url": "https://designsafe.tapis.io"}}
    target.list_jobs.return_value = [JobSummary("remote", "remote-study", "2026-01-01T00:00:00Z",
                                               JobStatus("running", "RUNNING"))]
    login = Mock(return_value=target)
    monkeypatch.setitem(tracking._CONNECTORS, "tacc", login)

    async def exercise():
        app = JobTracker(registry=store)
        app.suspend = nullcontext
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.query_one(DataTable).row_count == 0
            await pilot.press("l")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.query_one(DataTable).row_count == 1
            assert app.selected().id == "remote" and app.selected().state == "running"
            await pilot.press("r")
            await app.workers.wait_for_complete()
            assert len(store.list()) == 1
            target.job.assert_not_called()  # list response already contains current status
    asyncio.run(exercise())
    assert login.call_args.args[0].connection["app_id"] == "job-tracking"


def test_cli_remote_list_discovers_without_existing_ids(store, monkeypatch, capsys):
    import sys
    from femora.jobs.__main__ import main
    target = Mock()
    target.tracking_metadata.return_value = {"platform": "tacc", "connection": {
        "username": "user", "base_url": "https://designsafe.tapis.io"}}
    target.list_jobs.return_value = [JobSummary("remote", "study", "2026-01-01T00:00:00Z",
                                               JobStatus("pending", "QUEUED"))]
    login = Mock(return_value=target)
    monkeypatch.setattr(TACCPlatform, "login", login)
    monkeypatch.setattr(sys, "argv", ["jobs", "list", "--remote", "--json", "--app-id", "custom-app"])
    main()
    assert '"id": "remote"' in capsys.readouterr().out
    login.assert_called_once_with(app_id="custom-app", base_url="https://designsafe.tapis.io")
