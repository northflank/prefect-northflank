import asyncio
import time
from typing import TYPE_CHECKING, Dict, List, Optional

from anyio.abc import TaskStatus
from prefect.workers.base import (
    BaseJobConfiguration,
    BaseVariables,
    BaseWorker,
    BaseWorkerResult,
)
from pydantic import Field, PrivateAttr

from .client import NorthflankClient
from .credentials import Northflank
from .schemas import (  # type: ignore
    InfrastructureConfig,
    BillingConfig,
    ExternalDeployment,
    DeploymentConfig,
    JobSettings,
    JobCreationRequest,
    DockerConfig,
)

if TYPE_CHECKING:
    from prefect.client.schemas import FlowRun


class FlattenedNorthflankJobConfiguration(BaseJobConfiguration):
    """
    Flattened job configuration for Northflank worker that's compatible with Prefect's flat JSON schema requirements.
    """

    # Prefect-specific fields (not part of API schema)
    credentials: Northflank = Field(
        title="Northflank Credentials",
        default_factory=Northflank,
        description=(
            "The Northflank credentials used to connect to the API. "
            "If not provided, credentials will be inferred from "
            "the local environment."
        ),
    )
    project_id: Optional[str] = Field(
        default=None, description="The Northflank project ID where jobs will be created"
    )
    cleanup_job: Optional[bool] = Field(
        default=True, description="Whether to delete the job after completion"
    )

    # Basic job fields
    name: Optional[str] = Field(
        default=None, description="Name of the job (auto-generated if not provided)"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the job (auto-generated if not provided)",
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Tags to help identify and group the resource"
    )

    # Infrastructure configuration (flattened)
    infrastructure_architecture: Optional[str] = Field(
        default=None, description="CPU architecture to use for the job (x86 or arm)"
    )

    # Billing configuration (flattened)
    billing_deployment_plan: Optional[str] = Field(
        default="nf-compute-20", description="The ID of the deployment plan to use"
    )
    billing_gpu_enabled: Optional[bool] = Field(
        default=False, description="Whether GPU is enabled"
    )
    billing_gpu_type: Optional[str] = Field(
        default=None, description="Type of GPU to use"
    )
    billing_gpu_count: Optional[int] = Field(
        default=1, description="Number of GPUs to allocate"
    )
    billing_gpu_timesliced: Optional[bool] = Field(
        default=None, description="Whether to use timesliced GPU sharing"
    )

    # Deployment configuration (flattened)
    deployment_external_image_path: Optional[str] = Field(
        default=None, description="Container image path to deploy"
    )
    deployment_external_credentials: Optional[str] = Field(
        default=None, description="ID of registry credentials for private images"
    )
    deployment_internal_id: Optional[str] = Field(
        default=None, description="ID of the build service to deploy"
    )
    deployment_internal_branch: Optional[str] = Field(
        default=None, description="Branch to deploy"
    )
    deployment_internal_build_sha: Optional[str] = Field(
        default=None,
        description="Commit SHA to deploy, or 'latest' to deploy the most recent commit",
    )
    deployment_internal_build_id: Optional[str] = Field(
        default=None, description="ID of the build that should be deployed"
    )
    deployment_docker_config_type: Optional[str] = Field(
        default="customCommand", description="Docker configuration type"
    )
    deployment_docker_custom_command: Optional[str] = Field(
        default=None, description="Custom command to run"
    )

    # Runtime environment
    runtime_environment: Optional[Dict[str, str]] = Field(
        default=None, description="Runtime environment variables"
    )

    # Job settings (flattened)
    settings_backoff_limit: Optional[int] = Field(
        default=3, description="Number of retry attempts before marking job as failed"
    )
    settings_active_deadline_seconds: Optional[int] = Field(
        default=3600, description="Maximum runtime in seconds before job is terminated"
    )
    settings_run_on_source_change: Optional[str] = Field(
        default="never", description="When to run job on source changes"
    )

    _job_id: Optional[str] = PrivateAttr(default=None)

    def to_nested_config(self) -> JobCreationRequest:
        """Convert the flattened configuration to the nested structure required by the Northflank API."""
        from .schemas import Architecture, GpuConfig, GpuConfiguration

        infrastructure = None
        if self.infrastructure_architecture:
            arch = (
                Architecture.X86
                if self.infrastructure_architecture.lower() == "x86"
                else Architecture.ARM
            )
            infrastructure = InfrastructureConfig(architecture=arch)

        billing = None
        if any(
            [
                self.billing_deployment_plan,
                self.billing_gpu_enabled,
            ]
        ):
            gpu_config = None
            if self.billing_gpu_enabled:
                gpu_configuration = None
                if any(
                    [
                        self.billing_gpu_type,
                        self.billing_gpu_count,
                        self.billing_gpu_timesliced,
                    ]
                ):
                    gpu_configuration = GpuConfiguration(
                        gpuType=self.billing_gpu_type,
                        gpuCount=self.billing_gpu_count,
                        timesliced=self.billing_gpu_timesliced,
                    )
                gpu_config = GpuConfig(
                    enabled=self.billing_gpu_enabled,
                    configuration=gpu_configuration,
                )

            billing = BillingConfig(
                deploymentPlan=self.billing_deployment_plan,
                gpu=gpu_config,
            )

        deployment = None

        has_external = any(
            [
                self.deployment_external_image_path,
                self.deployment_external_credentials,
            ]
        )
        has_internal = any(
            [
                self.deployment_internal_id,
                self.deployment_internal_branch,
                self.deployment_internal_build_sha,
                self.deployment_internal_build_id,
            ]
        )

        external_deployment = None
        internal_deployment = None
        docker_config = None

        if has_external:
            external_deployment = ExternalDeployment(
                imagePath=self.deployment_external_image_path,
                credentials=self.deployment_external_credentials,
            )

        if has_internal:
            from .schemas import InternalDeployment

            internal_deployment = InternalDeployment(
                id=self.deployment_internal_id,
                branch=self.deployment_internal_branch,
                buildSHA=self.deployment_internal_build_sha,
                buildId=self.deployment_internal_build_id,
            )

        if any(
            [self.deployment_docker_config_type, self.deployment_docker_custom_command]
        ):
            docker_config = DockerConfig(
                configType=self.deployment_docker_config_type or "customCommand",
                customCommand=self.deployment_docker_custom_command,
            )

        if has_external or has_internal or docker_config:
            deployment = DeploymentConfig(
                external=external_deployment,
                internal=internal_deployment,
                docker=docker_config,
            )

        settings = None
        if any(
            [
                self.settings_backoff_limit is not None,
                self.settings_active_deadline_seconds is not None,
                self.settings_run_on_source_change,
            ]
        ):
            settings = JobSettings(
                backoffLimit=self.settings_backoff_limit,
                activeDeadlineSeconds=self.settings_active_deadline_seconds,
                runOnSourceChange=self.settings_run_on_source_change,
            )

        return JobCreationRequest(
            name=self.name or "",  # Will be set by the worker
            description=self.description,
            infrastructure=infrastructure,
            tags=self.tags,
            billing=billing,
            deployment=deployment,
            runtimeEnvironment=self.runtime_environment,
            settings=settings,
        )


class FlattenedNorthflankVariables(BaseVariables):
    """
    Flattened variables for Northflank worker pool configuration.
    """

    credentials: Northflank = Field(
        title="Northflank Credentials",
        default_factory=Northflank,
        description=(
            "The Northflank credentials used to connect to the API. "
            "If not provided, credentials will be inferred from "
            "the local environment."
        ),
    )
    project_id: Optional[str] = Field(
        default=None, description="The Northflank project ID where jobs will be created"
    )
    cleanup_job: Optional[bool] = Field(
        default=True, description="Whether to delete the job after completion"
    )

    name: Optional[str] = Field(
        default=None, description="Name of the job (auto-generated if not provided)"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the job (auto-generated if not provided)",
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Tags to help identify and group the resource"
    )

    # Infrastructure configuration (flattened)
    infrastructure_architecture: Optional[str] = Field(
        default=None, description="CPU architecture to use for the job (x86 or arm)"
    )

    # Billing configuration (flattened)
    billing_deployment_plan: Optional[str] = Field(
        default="nf-compute-20", description="The ID of the deployment plan to use"
    )
    billing_gpu_enabled: Optional[bool] = Field(
        default=False, description="Whether GPU is enabled"
    )
    billing_gpu_type: Optional[str] = Field(
        default=None, description="Type of GPU to use"
    )
    billing_gpu_count: Optional[int] = Field(
        default=1, description="Number of GPUs to allocate"
    )
    billing_gpu_timesliced: Optional[bool] = Field(
        default=None, description="Whether to use timesliced GPU sharing"
    )

    # Deployment configuration (flattened)
    deployment_external_image_path: Optional[str] = Field(
        default=None, description="Container image path to deploy"
    )
    deployment_external_credentials: Optional[str] = Field(
        default=None, description="ID of registry credentials for private images"
    )
    deployment_internal_id: Optional[str] = Field(
        default=None, description="ID of the build service to deploy"
    )
    deployment_internal_branch: Optional[str] = Field(
        default=None, description="Branch to deploy"
    )
    deployment_internal_build_sha: Optional[str] = Field(
        default=None,
        description="Commit SHA to deploy, or 'latest' to deploy the most recent commit",
    )
    deployment_internal_build_id: Optional[str] = Field(
        default=None, description="ID of the build that should be deployed"
    )
    deployment_docker_config_type: Optional[str] = Field(
        default="customCommand", description="Docker configuration type"
    )
    deployment_docker_custom_command: Optional[str] = Field(
        default=None, description="Custom command to run"
    )

    # Build configuration (flattened)
    build_configuration_docker_credentials: Optional[List[str]] = Field(
        default=None, description="List of docker credential IDs"
    )

    # Runtime environment
    runtime_environment: Optional[Dict[str, str]] = Field(
        default=None, description="Runtime environment variables"
    )

    # Job settings (flattened)
    settings_backoff_limit: Optional[int] = Field(
        default=3, description="Number of retry attempts before marking job as failed"
    )
    settings_active_deadline_seconds: Optional[int] = Field(
        default=3600, description="Maximum runtime in seconds before job is terminated"
    )
    settings_run_on_source_change: Optional[str] = Field(
        default="never", description="When to run job on source changes"
    )


class NorthflankWorkerResult(BaseWorkerResult):
    """
    The result of a Northflank worker job.
    """

    execution_time: Optional[float] = Field(
        default=None, description="Job execution time in seconds"
    )
    job_id: Optional[str] = Field(default=None, description="Northflank job ID")
    run_id: Optional[str] = Field(default=None, description="Northflank run ID")


class NorthflankWorker(
    BaseWorker[
        FlattenedNorthflankJobConfiguration,
        FlattenedNorthflankVariables,
        NorthflankWorkerResult,
    ]
):
    """
    A Prefect worker that executes flow runs as jobs on the Northflank platform using a flattened configuration schema.
    """

    type = "northflank"
    job_configuration = FlattenedNorthflankJobConfiguration
    job_configuration_variables = FlattenedNorthflankVariables
    _description = "Execute flow runs as containerized jobs on Northflank."
    _display_name = "Northflank"
    _documentation_url = "https://github.com/northflank/prefect-northflank"
    _logo_url = "https://assets.northflank.com/Group_1410119476_2_b23babb7fd.png"

    async def _cancel_job_run(
        self,
        client: NorthflankClient,
        project_id: str,
        job_id: str,
        run_id: str,
        logger,
    ) -> None:
        """Attempt to cancel a Northflank job run."""
        try:
            logger.info(f"Attempting to cancel job run {run_id}")
            await client.abort_job_run(project_id, job_id, run_id)
            logger.info(f"Successfully requested cancellation of job run {run_id}")
        except Exception as e:
            logger.warning(
                f"Failed to cancel job run {run_id}: {e}. Job may continue running."
            )

    async def run(
        self,
        flow_run: "FlowRun",
        configuration: FlattenedNorthflankJobConfiguration,
        task_status: Optional[TaskStatus] = None,
    ) -> NorthflankWorkerResult:
        """
        Runs the flow run on Northflank and waits for it to complete.
        """
        start_time = time.time()
        logger = self.get_flow_run_logger(flow_run)

        if not configuration.credentials or not configuration.credentials.api_token:
            error_msg = "Northflank API token is required but not provided"
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not configuration.project_id:
            error_msg = "Northflank project ID is required but not provided"
            logger.error(error_msg)
            raise ValueError(error_msg)

        api_token = configuration.credentials.api_token.get_secret_value()
        base_url = configuration.credentials.base_url

        logger.info(f"Initializing Northflank worker for flow run {flow_run.id}")
        logger.debug(f"Using Northflank API base URL: {base_url}")
        logger.debug(f"Project ID: {configuration.project_id}")

        job_id = None
        run_id = None

        try:
            async with NorthflankClient(api_token, base_url) as client:
                short_id = str(flow_run.id).split("-")[0]
                job_name = f"pf-{flow_run.name}-{short_id}"
                logger.info(f"Creating Northflank job: {job_name}")

                if configuration.command:
                    command = configuration.command.split()
                else:
                    command = [
                        "python",
                        "-m",
                        "prefect.engine",
                        "execute-flow-run",
                        str(flow_run.id),
                    ]

                base_env = configuration.env or {}
                user_env = configuration.runtime_environment or {}

                env = {}
                for k, v in {**base_env, **user_env}.items():
                    if v is not None:
                        env[k] = str(v)

                job_request = configuration.to_nested_config()

                job_request.name = job_name
                if not job_request.description:
                    job_request.description = f"Prefect job: {job_name}"

                job_request.runtime_environment = env

                # Only set default external deployment if no meaningful deployment config exists
                if not job_request.deployment or (
                    not job_request.deployment.external
                    and not job_request.deployment.internal
                ):
                    job_request.deployment = DeploymentConfig(
                        external=ExternalDeployment(
                            imagePath="prefecthq/prefect:3-python3.12"
                        ),
                        docker=DockerConfig(
                            configType="customCommand", customCommand=" ".join(command)
                        ),
                    )
                else:
                    # Handle docker config for existing deployment
                    if not job_request.deployment.docker:
                        job_request.deployment.docker = DockerConfig(
                            configType="customCommand", customCommand=" ".join(command)
                        )
                    else:
                        job_request.deployment.docker.custom_command = " ".join(command)

                try:
                    job_id = await client.create_job(
                        project_id=configuration.project_id,
                        job_request=job_request,
                    )
                    logger.info(f"Successfully created job with ID: {job_id}")
                except Exception as e:
                    error_msg = f"Failed to create Northflank job: {e}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

                try:
                    logger.info(f"Starting job run for job: {job_id}")
                    run_id = await client.start_job_run(
                        project_id=configuration.project_id,
                        job_id=job_id,
                        runtime_env_overrides={},
                    )
                    identifier = f"{job_id}:{run_id}"
                    logger.info(f"Successfully started job run with ID: {run_id}")
                except Exception as e:
                    error_msg = f"Failed to start job run for job {job_id}: {e}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

                if task_status:
                    task_status.started(identifier)

                timeout = (
                    job_request.settings.active_deadline_seconds
                    if job_request.settings
                    and job_request.settings.active_deadline_seconds
                    else 3600
                )
                logger.info(f"Monitoring job run {run_id} for completion...")
                logger.debug(f"Using timeout of {timeout} seconds")

                try:
                    result = await asyncio.wait_for(
                        client.wait_for_completion(
                            project_id=configuration.project_id,
                            job_id=job_id,
                            run_id=run_id,
                            timeout=timeout,
                        ),
                        timeout=timeout,
                    )

                    status = result.get("status", "UNKNOWN")
                    logger.info(f"Job run completed with status: {status}")

                    execution_time = time.time() - start_time

                    if status == "SUCCESS":
                        logger.info(
                            f"Flow run {flow_run.id} executed successfully on Northflank"
                        )
                        return NorthflankWorkerResult(
                            status_code=0,
                            identifier=identifier,
                            execution_time=execution_time,
                            job_id=job_id,
                            run_id=run_id,
                        )
                    elif status == "FAILED":
                        logger.error(f"Job run failed with status: {status}")
                        return NorthflankWorkerResult(
                            status_code=-1,
                            identifier=identifier,
                            execution_time=execution_time,
                            job_id=job_id,
                            run_id=run_id,
                        )
                    else:
                        logger.warning(
                            f"Job run completed with unexpected status: {status}"
                        )
                        return NorthflankWorkerResult(
                            status_code=-1,
                            identifier=identifier,
                            execution_time=execution_time,
                            job_id=job_id,
                            run_id=run_id,
                        )

                except asyncio.TimeoutError as e:
                    error_msg = f"Job run {run_id} timed out after {timeout} seconds"
                    logger.error(error_msg)
                    await self._cancel_job_run(
                        client, configuration.project_id, job_id, run_id, logger
                    )
                    raise RuntimeError(error_msg) from e
                except asyncio.CancelledError:
                    logger.info(
                        f"Job run {run_id} was cancelled, attempting to cancel Northflank job"
                    )
                    await self._cancel_job_run(
                        client, configuration.project_id, job_id, run_id, logger
                    )
                    raise
                except Exception as e:
                    error_msg = f"Failed to monitor job run {run_id}: {e}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

        except asyncio.CancelledError:
            logger.info(f"Flow run {flow_run.id} was cancelled")
            if job_id and run_id:
                async with NorthflankClient(api_token, base_url) as cancel_client:
                    await self._cancel_job_run(
                        cancel_client, configuration.project_id, job_id, run_id, logger
                    )
            raise
        except Exception as e:
            logger.error(
                f"Northflank worker execution failed for flow run {flow_run.id}: {e}"
            )
            raise
        finally:
            if job_id and configuration.cleanup_job:
                try:
                    logger.info(f"Cleaning up job: {job_id}")
                    async with NorthflankClient(api_token, base_url) as client:
                        await client.delete_job(configuration.project_id, job_id)
                    logger.info(f"Successfully cleaned up job: {job_id}")
                except Exception as e:
                    logger.warning(
                        f"Failed to cleanup job {job_id}: {e}. Manual cleanup may be required."
                    )
