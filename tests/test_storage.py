"""Ephemeral storage and /dev/shm reach the job creation request, and stay out of it when unset."""

import pytest
from pydantic import ValidationError

from prefect_northflank.credentials import Northflank
from prefect_northflank.worker import (
    FlattenedNorthflankJobConfiguration,
    FlattenedNorthflankVariables,
    NorthflankWorker,
)


def configuration(**storage) -> FlattenedNorthflankJobConfiguration:
    return FlattenedNorthflankJobConfiguration(
        credentials=Northflank(api_token="token"),
        project_id="project",
        deployment_external_image_path="prefecthq/prefect:3-latest",
        **storage,
    )


def test_unset_storage_leaves_the_platform_default():
    data = configuration().to_nested_config().to_api_dict()
    assert "storage" not in data["deployment"]


def test_ephemeral_storage_is_sent_in_mb():
    data = (
        configuration(deployment_storage_ephemeral_storage_size=8192)
        .to_nested_config()
        .to_api_dict()
    )
    assert data["deployment"]["storage"] == {"ephemeralStorage": {"storageSize": 8192}}


def test_shm_size_is_sent_on_its_own_or_with_ephemeral_storage():
    data = (
        configuration(deployment_storage_shm_size=512).to_nested_config().to_api_dict()
    )
    assert data["deployment"]["storage"] == {"shmSize": 512}
    data = (
        configuration(
            deployment_storage_ephemeral_storage_size=2048,
            deployment_storage_shm_size=256,
        )
        .to_nested_config()
        .to_api_dict()
    )
    assert data["deployment"]["storage"] == {
        "ephemeralStorage": {"storageSize": 2048},
        "shmSize": 256,
    }


def minimum(schema: dict) -> int | None:
    """An Optional field's bound sits in its anyOf branch, a plain one's at the top."""
    if "minimum" in schema:
        return schema["minimum"]
    return next((s["minimum"] for s in schema.get("anyOf", []) if "minimum" in s), None)


def test_the_work_pool_template_offers_both_variables():
    template = NorthflankWorker.get_default_base_job_template()
    properties = template["variables"]["properties"]
    assert minimum(properties["deployment_storage_ephemeral_storage_size"]) == 1024
    assert minimum(properties["deployment_storage_shm_size"]) == 64
    assert template["job_configuration"][
        "deployment_storage_ephemeral_storage_size"
    ] == ("{{ deployment_storage_ephemeral_storage_size }}")


def test_the_variables_refuse_less_than_the_platform_minimum():
    with pytest.raises(ValidationError):
        FlattenedNorthflankVariables(
            credentials=Northflank(api_token="token"),
            deployment_storage_ephemeral_storage_size=512,
        )


@pytest.mark.parametrize(
    "model", [FlattenedNorthflankVariables, FlattenedNorthflankJobConfiguration]
)
@pytest.mark.parametrize(
    "field, value",
    [
        ("deployment_storage_ephemeral_storage_size", 1023),
        ("deployment_storage_ephemeral_storage_size", 0),
        ("deployment_storage_shm_size", 63),
        ("deployment_storage_shm_size", -1),
    ],
)
def test_storage_bounds_apply_to_all_configuration(model, field, value):
    with pytest.raises(ValidationError):
        model(credentials=Northflank(api_token="token"), **{field: value})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "image_config",
    [
        {},
        {"deployment_external_image_path": "python:3.12"},
        {"deployment_internal_id": "build-service"},
    ],
)
async def test_worker_sends_storage_to_api_with_every_image_source(image_config):
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    from uuid import uuid4

    import httpx
    import respx

    config = FlattenedNorthflankJobConfiguration(
        credentials=Northflank(api_token="token"),
        project_id="project",
        cleanup_job=False,
        deployment_storage_ephemeral_storage_size=8192,
        deployment_storage_shm_size=256,
        **image_config,
    )
    base = "https://api.northflank.com/v1/projects/project/jobs"
    with respx.mock as router:
        create = router.post(base).mock(
            return_value=httpx.Response(200, json={"data": {"id": "job"}})
        )
        router.post(f"{base}/job/runs").mock(
            return_value=httpx.Response(200, json={"data": {"id": "run"}})
        )
        router.get(f"{base}/job/runs/run").mock(
            return_value=httpx.Response(200, json={"data": {"status": "SUCCESS"}})
        )
        with patch.object(NorthflankWorker, "get_flow_run_logger", return_value=Mock()):
            result = await NorthflankWorker(work_pool_name="test").run(
                SimpleNamespace(id=uuid4(), name="storage-test"), config
            )
        assert result.status_code == 0
        deployment = json.loads(create.calls.last.request.content)["deployment"]
        assert deployment["storage"] == {
            "ephemeralStorage": {"storageSize": 8192},
            "shmSize": 256,
        }
        if not image_config:
            assert (
                deployment["external"]["imagePath"] == "prefecthq/prefect:3-python3.12"
            )
