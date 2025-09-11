from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class Architecture(str, Enum):
    """CPU Architecture options."""

    X86 = "x86"
    ARM = "arm"


class InfrastructureConfig(BaseModel):
    """Infrastructure configuration."""

    architecture: Optional[Architecture] = Field(
        default=None, description="CPU architecture to use for the job"
    )


class GpuConfiguration(BaseModel):
    """GPU configuration details."""

    gpu_type: Optional[str] = Field(
        default=None, description="Type of GPU to use", alias="gpuType"
    )
    gpu_count: Optional[int] = Field(
        default=1, description="Number of GPUs to allocate", alias="gpuCount"
    )
    timesliced: Optional[bool] = Field(
        default=None, description="Whether to use timesliced GPU sharing"
    )


class GpuConfig(BaseModel):
    """GPU configuration."""

    enabled: bool = Field(default=False, description="Whether GPU is enabled")
    configuration: Optional[GpuConfiguration] = Field(
        default=None, description="GPU configuration details (optional)"
    )


class BillingConfig(BaseModel):
    """Billing configuration."""

    deployment_plan: Optional[str] = Field(
        default=None,
        description="The ID of the deployment plan to use",
        alias="deploymentPlan",
    )
    gpu: Optional[GpuConfig] = Field(default=None, description="GPU configuration")


class ExternalDeployment(BaseModel):
    """External image deployment configuration."""

    image_path: Optional[str] = Field(
        default=None, description="Container image path to deploy", alias="imagePath"
    )
    credentials: Optional[str] = Field(
        default=None, description="ID of registry credentials for private images"
    )


class InternalDeployment(BaseModel):
    """Internal image deployment configuration from build service."""

    id: Optional[str] = Field(
        default=None, description="ID of the build service to deploy"
    )
    branch: Optional[str] = Field(default=None, description="Branch to deploy")
    build_sha: Optional[str] = Field(
        default=None, description="Commit SHA to deploy, or 'latest' to deploy the most recent commit", alias="buildSHA"
    )
    build_id: Optional[str] = Field(
        default=None, description="ID of the build that should be deployed", alias="buildId"
    )


class DockerConfig(BaseModel):
    """Docker runtime configuration."""

    model_config = ConfigDict(populate_by_name=True)

    config_type: str = Field(
        default="customCommand",
        description="Docker configuration type",
        alias="configType",
    )
    custom_command: Optional[str] = Field(
        default=None, description="Custom command to run", alias="customCommand"
    )


class DeploymentConfig(BaseModel):
    """Deployment configuration."""

    external: Optional[ExternalDeployment] = Field(
        default=None, description="External image deployment configuration"
    )
    internal: Optional[InternalDeployment] = Field(
        default=None,
        description="Internal image deployment configuration from build service",
    )
    docker: Optional[DockerConfig] = Field(
        default=None, description="Docker runtime configuration"
    )


class BuildConfiguration(BaseModel):
    """Build configuration."""

    docker_credentials: Optional[List[str]] = Field(
        default=None,
        description="List of docker credential IDs",
        alias="dockerCredentials",
    )


class JobSettings(BaseModel):
    """Job settings configuration."""

    backoff_limit: Optional[int] = Field(
        default=3,
        description="Number of retry attempts before marking job as failed",
        alias="backoffLimit",
    )
    active_deadline_seconds: Optional[int] = Field(
        default=3600,
        description="Maximum runtime in seconds before job is terminated",
        alias="activeDeadlineSeconds",
    )
    run_on_source_change: Optional[str] = Field(
        default="never",
        description="When to run job on source changes",
        alias="runOnSourceChange",
    )


class JobCreationRequest(BaseModel):
    """Complete job creation request matching Northflank API schema."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Name of the job")
    description: Optional[str] = Field(
        default=None, description="Description of the job"
    )
    infrastructure: Optional[InfrastructureConfig] = Field(
        default=None, description="Infrastructure configuration"
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Tags to help identify and group the resource"
    )
    billing: Optional[BillingConfig] = Field(
        default=None,
        description="Billing configuration including plans and GPU settings",
    )
    deployment: Optional[DeploymentConfig] = Field(
        default=None, description="Deployment configuration"
    )
    runtime_environment: Optional[Dict[str, str]] = Field(
        default=None,
        description="Runtime environment variables",
        alias="runtimeEnvironment",
    )
    settings: Optional[JobSettings] = Field(
        default=None, description="Job execution settings"
    )

    def validate_deployment(self) -> None:
        if not self.deployment:
            raise ValueError("Deployment configuration is required")

        has_external = self.deployment.external is not None
        has_internal = self.deployment.internal is not None

        if not has_external and not has_internal:
            raise ValueError(
                "Must specify either external image or internal build service deployment"
            )
        if has_external and has_internal:
            raise ValueError(
                "Cannot specify both external image and internal build service deployment"
            )

    def to_api_dict(self) -> Dict[str, Any]:
        self.validate_deployment()

        return self.model_dump(by_alias=True, exclude_none=True, exclude_unset=False)
