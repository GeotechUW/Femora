"""Public submission API tests; all transport is mocked."""

from dataclasses import replace
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import femora as fm
from femora.jobs.platforms import TACCPlatform, TACCSettings, TACCJob, RemoteSubmissionError
from femora.jobs.platforms.tacc import SubmissionValidationError
from femora.jobs.platforms.tacc_remote import JobCleanupPlan


@pytest.fixture
def client():
    client = Mock()
    client.base_url = "https://designsafe.tapis.io"
    client.username = "test-user"
    client.apps.getApp.return_value = {"jobAttributes": {
        "execSystemId": "stampede3", "isMpi": False}}
    client.systems.getSystem.return_value = {
        "enabled": True, "canExec": True, "batchLogicalQueues": [{
            "name": "skx-dev", "minNodeCount": 1, "maxNodeCount": 16,
            "minCoresPerNode": 1, "maxCoresPerNode": 48, "minMinutes": 1, "maxMinutes": 120}]}
    error = RuntimeError("missing")
    error.response = SimpleNamespace(status_code=404)
    client.files.listFiles.side_effect = error
    client.jobs.submitJob.return_value = SimpleNamespace(uuid="job-id")
    return client


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "workflow.py"
    path.write_text("raise RuntimeError('must not execute locally')\n")
    return path


def settings():
    return TACCSettings("stampede3", "skx-dev", "PROJECT", 1, 48, 20)


def platform(client):
    return TACCPlatform(client, app_id="app", app_version="0.1",
                        storage_system="storage", input_directory="user/jobs",
                        on_validation=lambda report: None)


def test_public_source_submit_validates_before_upload(client, source):
    uploaded = []
    client.files.insert.side_effect = lambda **kw: uploaded.append(kw["file"].read())
    job = fm.submit(source=source, platform=platform(client), settings=settings())
    assert job.id == "job-id"
    names = [c[0] for c in client.mock_calls]
    assert names.index("systems.getSystem") < names.index("files.mkdir") < names.index("files.insert") < names.index("jobs.submitJob")
    request = client.jobs.submitJob.call_args.kwargs
    assert request["execSystemLogicalQueue"] == "skx-dev"
    assert request["coresPerNode"] == 48
    with ZipFile(io.BytesIO(uploaded[0])) as archive:
        assert archive.read("workflow.py") == source.read_bytes()


def test_invalid_request_never_uploads(client, source):
    with pytest.raises(SubmissionValidationError):
        fm.submit(source=source, platform=platform(client), settings=replace(settings(), cores_per_node=100))
    client.files.mkdir.assert_not_called()
    client.files.insert.assert_not_called()
    client.jobs.submitJob.assert_not_called()


def test_generic_api_supports_other_provider_and_removes_temporary_archive(source):
    class AnotherProvider:
        def submit(self, bundle, settings):
            self.path = bundle
            assert bundle.is_file() and settings == {"region": "test"}
            return "handle"
    provider = AnotherProvider()
    assert fm.submit(source=source, platform=provider, settings={"region": "test"}) == "handle"
    assert not provider.path.exists()


def test_existing_bundle_and_argument_validation(client, source, tmp_path):
    archive = fm.jobs.bundle(source=source, destination=tmp_path / "bundle.zip", inputs={})
    assert fm.submit(bundle=archive, platform=platform(client), settings=settings()).id == "job-id"
    for kwargs in ({}, {"source": source, "bundle": archive}, {"bundle": archive, "inputs": {}}):
        with pytest.raises(ValueError):
            fm.submit(platform=platform(client), settings=settings(), **kwargs)


def test_submissions_use_distinct_directories(client, source):
    target = platform(client)
    fm.submit(source=source, platform=target, settings=settings())
    fm.submit(source=source, platform=target, settings=settings())
    paths = [c.kwargs["path"] for c in client.files.insert.call_args_list]
    assert len(set(paths)) == 2


def test_submit_error_is_not_retried_and_has_recovery_info(client, source):
    client.jobs.submitJob.side_effect = RuntimeError("secret-token")
    with pytest.raises(RemoteSubmissionError) as error:
        fm.submit(source=source, platform=platform(client), settings=settings())
    assert "secret-token" not in str(error.value)
    assert error.value.bundle_url.startswith("tapis://storage/user/jobs/")
    client.jobs.submitJob.assert_called_once()
    client.files.delete.assert_not_called()


def test_upload_failure_does_not_submit(client, source):
    client.files.insert.side_effect = RuntimeError("upload failed")
    with pytest.raises(RuntimeError):
        fm.submit(source=source, platform=platform(client), settings=settings())
    client.jobs.submitJob.assert_not_called()


@pytest.mark.parametrize("native,state", [("QUEUED", "pending"), ("RUNNING", "running"),
    ("ARCHIVING", "running"), ("FINISHED", "succeeded"), ("FAILED", "failed"),
    ("CANCELLED", "cancelled"), ("FUTURE_STATE", "unknown")])
def test_job_status_and_reconnect(client, native, state):
    client.jobs.getJob.return_value = {"status": native, "lastMessage": "message"}
    job = platform(client).job("known-id")
    assert job.status().state == state
    assert job.status().native_state == native
    client.jobs.submitJob.assert_not_called()
    job.cancel()
    client.jobs.cancelJob.assert_called_once_with(jobUuid="known-id")


JOB_UUID = "94a706b0-0306-4cbb-88ca-17e9d18b2a91-007"


def cleanup_job(client):
    client.username = "test-user"
    client.jobs.getJob.return_value = {
        "owner": "test-user", "status": "FINISHED", "execSystemId": "stampede3",
        "execSystemExecDir": f"/scratch/08189/test-user/tapis/{JOB_UUID}",
        "archiveSystemId": "designsafe.storage.default",
        "archiveSystemDir": f"/test-user/tapis-jobs-archive/2026-09-28Z/{JOB_UUID}",
    }
    return TACCJob(JOB_UUID, client)


def test_cleanup_removes_only_job_folders_then_hides_in_tapis(client):
    job = cleanup_job(client)
    plan = job.cleanup_plan()
    assert plan == JobCleanupPlan(JOB_UUID,
        ("stampede3", f"/scratch/08189/test-user/tapis/{JOB_UUID}"),
        ("designsafe.storage.default", f"/test-user/tapis-jobs-archive/2026-09-28Z/{JOB_UUID}"))
    client.files.listFiles.side_effect = None
    client.files.listFiles.return_value = ["output"]
    assert job.cleanup(plan) == (plan.scratch[1], plan.archive[1])
    assert [call.kwargs for call in client.files.delete.call_args_list] == [
        {"systemId": system, "path": path} for system, path in (plan.scratch, plan.archive)]
    client.jobs.hideJob.assert_called_once_with(jobUuid=JOB_UUID)
    names = [call[0] for call in client.mock_calls]
    assert names.index("files.delete") < names.index("jobs.hideJob")


def test_cleanup_skips_missing_folders_and_still_hides(client):
    job = cleanup_job(client)
    plan = job.cleanup_plan()
    assert job.cleanup(plan) == ()
    client.files.delete.assert_not_called()
    client.jobs.hideJob.assert_called_once_with(jobUuid=JOB_UUID)


@pytest.mark.parametrize("field,value", [
    ("owner", "someone-else"), ("status", "RUNNING"),
    ("execSystemExecDir", "/scratch/08189/test-user/tapis"),
    ("execSystemExecDir", f"/scratch/08189/test-user/tapis/{JOB_UUID}/output"),
    ("execSystemExecDir", f"/scratch/08189/other/tapis/{JOB_UUID}"),
    ("archiveSystemDir", "/test-user/tapis-jobs-archive"),
    ("archiveSystemDir", f"/test-user/tapis-jobs-archive/2026-09-28Z/{JOB_UUID}/output"),
    ("archiveSystemId", "other-system"),
])
def test_cleanup_rejects_unsafe_or_active_job_without_writes(client, field, value):
    job = cleanup_job(client)
    client.jobs.getJob.return_value[field] = value
    with pytest.raises(ValueError):
        job.cleanup_plan()
    client.files.delete.assert_not_called()
    client.jobs.hideJob.assert_not_called()


def test_cleanup_rechecks_paths_and_stops_on_delete_error(client):
    job = cleanup_job(client)
    plan = job.cleanup_plan()
    client.jobs.getJob.return_value["archiveSystemDir"] = None
    with pytest.raises(ValueError, match="changed"):
        job.cleanup(plan)
    client.files.delete.assert_not_called()
    client.jobs.hideJob.assert_not_called()

    cleanup_job(client)
    client.files.listFiles.side_effect = None
    client.files.listFiles.return_value = ["output"]
    client.files.delete.side_effect = PermissionError("denied")
    with pytest.raises(PermissionError):
        job.cleanup(plan)
    client.jobs.hideJob.assert_not_called()


def test_job_download_no_redirect_no_overwrite(client, tmp_path, monkeypatch):
    import requests
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as z:
        z.writestr("results.zip", b"nested archive")
    response = Mock(status_code=200)
    response.headers = {"Content-Length": str(len(buffer.getvalue()))}
    response.iter_content.return_value = [buffer.getvalue()]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    get = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", get)
    client.jobs.getJob.return_value = {"status": "FINISHED"}
    client.access_token.access_token = "fake"
    job = TACCJob("id", client)
    path = tmp_path / "out.zip"
    progress = Mock()
    assert job.download(path, progress=progress) == path
    assert path.read_bytes() == buffer.getvalue()
    events = [call.args for call in progress.call_args_list]
    assert events[0] == ("receiving", 0, len(buffer.getvalue()))
    assert ("receiving", len(buffer.getvalue()), len(buffer.getvalue())) in events
    assert ("validating", len(buffer.getvalue()), len(buffer.getvalue())) in events
    assert events[-1] == ("saving", len(buffer.getvalue()), len(buffer.getvalue()))
    assert get.call_args.kwargs["allow_redirects"] is False
    with pytest.raises(FileExistsError):
        job.download(path)
    assert get.call_count == 1


def test_job_download_progress_without_content_length(client, tmp_path, monkeypatch):
    import requests
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("result.txt", "ok")
    response = Mock(status_code=200)
    response.headers = {}
    response.iter_content.return_value = [buffer.getvalue()]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    client.jobs.getJob.return_value = {"status": "FINISHED"}
    client.access_token.access_token = "fake"
    progress = Mock()
    TACCJob("id", client).download(tmp_path / "out.zip", progress=progress)
    assert ("receiving", 0, None) in [call.args for call in progress.call_args_list]
    assert ("receiving", len(buffer.getvalue()), None) in [call.args for call in progress.call_args_list]


def factory_for_packaging():
    raise RuntimeError("must not run locally")


def test_function_factory_packaged_not_called():
    provider = Mock()
    def check(bundle, settings):
        import json
        with ZipFile(bundle) as archive:
            assert json.loads(archive.read("bundle.json"))["entrypoint"] == "factory_for_packaging"
        return "job"
    provider.submit.side_effect = check
    assert fm.submit(function=factory_for_packaging, platform=provider, settings={}) == "job"
    with pytest.raises(ValueError, match="top-level"):
        fm.submit(function=lambda: None, platform=provider, settings={})
