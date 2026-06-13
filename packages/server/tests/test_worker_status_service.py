"""Tests for worker status queue introspection."""

from __future__ import annotations

import pickle
from pathlib import Path

from arq.connections import serialize_job
from contactsafe_server.services.worker_status_service import _function_name_from_job


def test_function_name_from_job_reads_arq_payload_without_unpickling() -> None:
    raw: bytes = serialize_job("enrich_org", (), {}, None, 123)

    assert _function_name_from_job(raw) == "enrich_org"


def test_function_name_from_job_does_not_execute_pickle_payload(tmp_path: Path) -> None:
    marker_path: Path = tmp_path / "pickle-executed"

    class MaliciousJob(dict[str, str]):
        def __reduce__(self) -> tuple[object, tuple[str]]:
            return (marker_path.write_text, ("executed",))

    raw: bytes = pickle.dumps(MaliciousJob({"f": "enrich_org"}))

    assert _function_name_from_job(raw) is None
    assert not marker_path.exists()
