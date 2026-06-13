import os
import pickle
from pathlib import Path

from arq.jobs import serialize_job

from contactsafe_server.services.worker_status_service import _function_name_from_job


def test_function_name_from_arq_job_without_unpickling() -> None:
    raw: bytes = serialize_job("enrich_org", ("arg",), {}, None, 123)

    assert _function_name_from_job(raw) == "enrich_org"


def test_function_name_from_job_does_not_execute_malicious_pickle(tmp_path: Path) -> None:
    marker: Path = tmp_path / "pickle_executed"

    class Payload:
        def __reduce__(self) -> tuple[object, tuple[str]]:
            return (os.system, (f"touch {marker}",))

    raw: bytes = pickle.dumps({"t": None, "f": Payload(), "a": (), "k": {}, "et": 123})

    assert _function_name_from_job(raw) is None
    assert not marker.exists()
