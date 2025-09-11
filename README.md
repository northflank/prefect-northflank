# prefect-northflank

[![PyPI version](https://badge.fury.io/py/prefect-northflank.svg)](https://badge.fury.io/py/prefect-northflank)

Prefect integrations for running flows on the [Northflank](https://northflank.com) platform.

This collection provides a Prefect worker that can execute flow runs as containerized jobs on Northflank's cloud platform, giving you powerful orchestration capabilities with Northflank's container-native infrastructure.

## Installation

Install `prefect-northflank` with pip:

```bash
pip install prefect-northflank
```

## Quick Start

1. **Set up Northflank credentials**:
   ```python
   from prefect_northflank import Northflank

   credentials = Northflank(
       api_token="your-northflank-api-token",
   )
   credentials.save("northflank-creds")
   ```

2. **Create a work pool**:
   ```bash
   prefect work-pool create --type northflank my-northflank-pool
   ```

3. **Configure your deployment** (prefect.yaml):
   ```yaml
   deployments:
   - name: my-northflank-deployment
     entrypoint: flows.py:my_flow
     work_pool:
       name: my-northflank-pool
       job_variables:
         credentials: "{{ prefect.blocks.northflank.northflank-creds }}"
         project_id: "your-northflank-project-id"
         deployment_external_image_path: "prefecthq/prefect:3-python3.12"
         billing_deployment_plan: "nf-compute-20"
   ```

4. **Start a worker**:
   ```bash
   prefect worker start --pool my-northflank-pool
   ```

5. **Deploy and run your flow**:
   ```bash
   prefect deploy --all
   prefect deployment run 'my-flow/my-northflank-deployment'
   ```

## Configuration

### Flattened Configuration Structure

The Northflank worker uses a flattened configuration structure to work with Prefect's JSON schema requirements. Complex nested objects are flattened using underscore notation:

- `billing.deploymentPlan` → `billing_deployment_plan`
- `deployment.external.imagePath` → `deployment_external_image_path`
- `settings.activeDeadlineSeconds` → `settings_active_deadline_seconds`

This allows for easier configuration in YAML files and work pools while maintaining compatibility with the full Northflank API.

### Worker Configuration

The Northflank worker supports the following configuration options:

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| **Core Configuration** | | | |
| `credentials` | Northflank | API credentials | Required |
| `project_id` | str | Northflank project ID | Required |
| `cleanup_job` | bool | Delete job after completion | True |
| `name` | str | Job name | Auto-generated |
| `description` | str | Job description | Auto-generated |
| `tags` | List[str] | Resource tags | None |
| **Infrastructure** | | | |
| `infrastructure_architecture` | str | CPU architecture (x86/arm) | None |
| **Billing** | | | |
| `billing_deployment_plan` | str | Resource allocation plan | "nf-compute-20" |
| `billing_gpu_enabled` | bool | Enable GPU support | False |
| `billing_gpu_type` | str | GPU type | None |
| `billing_gpu_count` | int | Number of GPUs | 1 |
| `billing_gpu_timesliced` | bool | Timesliced GPU sharing | None |
| **External Deployment** | | | |
| `deployment_external_image_path` | str | Container image path | None |
| `deployment_external_credentials` | str | Registry credentials ID | None |
| **Internal Deployment** | | | |
| `deployment_internal_id` | str | Build service ID | None |
| `deployment_internal_branch` | str | Git branch | None |
| `deployment_internal_build_sha` | str | Commit SHA to deploy | None |
| `deployment_internal_build_id` | str | Build ID to deploy | None |
| **Docker Configuration** | | | |
| `deployment_docker_config_type` | str | Docker config type | "customCommand" |
| `deployment_docker_custom_command` | str | Custom command | None |
| **Runtime** | | | |
| `runtime_environment` | Dict[str, str] | Environment variables | None |
| **Settings** | | | |
| `settings_backoff_limit` | int | Retry attempts | 3 |
| `settings_active_deadline_seconds` | int | Job timeout (seconds) | 3600 |
| `settings_run_on_source_change` | str | Source change trigger | "never" |

### Deployment Types

The Northflank worker supports two deployment strategies. Only one should be specified per job. If none is configured, the worker defaults to external deployment with the Prefect image.

#### 1. External Image Deployment (Default)
Deploy from a pre-built container image from any registry:

```yaml
job_variables:
  deployment_external_image_path: "prefecthq/prefect:3-python3.12"
  deployment_external_credentials: "my-registry-creds-id"  # Optional for private registries
```

#### 2. Internal Build Service Deployment
Deploy from Northflank's build service output:

```yaml
job_variables:
  deployment_internal_id: "build-service-123"
  deployment_internal_branch: "main"
  deployment_internal_build_sha: "latest"  # Or specific commit SHA
  # OR
  deployment_internal_build_id: "build-456"  # Specific build ID
```

#### Docker Configuration

Docker settings can be combined with either deployment type to control how the container runs:

```yaml
job_variables:
  deployment_external_image_path: "prefecthq/prefect:3-python3.12"
  deployment_docker_config_type: "customCommand"
  deployment_docker_custom_command: "python my_script.py"
```

### Environment Variables

The worker automatically injects Prefect environment variables into job containers:

- `PREFECT__FLOW_RUN_ID`: The unique flow run identifier (note the double underscore)
- `PREFECT_API_URL`: Prefect server/cloud API URL (if configured)
- `PREFECT_API_KEY`: Prefect API authentication key (if configured)
- Any other Prefect settings configured in the current environment

User-provided environment variables in `runtime_environment` take precedence over automatic variables.

## Examples

### Basic Flow Example

```python
from prefect import flow

@flow
def my_flow():
    print("Hello from Northflank!")
    return "Flow completed successfully"

if __name__ == "__main__":
    my_flow()
```

### GPU Configuration Example

```yaml
# prefect.yaml for GPU workloads
deployments:
  - name: gpu-training
    entrypoint: train_model.py:training_flow
    work_pool:
      name: northflank-gpu-pool
      job_variables:
        credentials: "{{ prefect.blocks.northflank.my-creds }}"
        project_id: "proj-123456"
        deployment_external_image_path: "nvidia/pytorch:23.10-py3"
        billing_deployment_plan: "nf-gpu-h100-80-1g"
        billing_gpu_enabled: true
        billing_gpu_type: "h100-80"
        billing_gpu_count: 2
        settings_active_deadline_seconds: 14400  # 4 hours
        runtime_environment:
          CUDA_VISIBLE_DEVICES: "0,1"
          TORCH_CUDA_ARCH_LIST: "8.9"
```

### Build Service Deployment Example

```yaml
# prefect.yaml for internal build service deployment
deployments:
  - name: my-build-deployment
    entrypoint: flows.py:my_flow
    work_pool:
      name: my-northflank-pool
      job_variables:
        credentials: "{{ prefect.blocks.northflank.my-creds }}"
        project_id: "proj-123456"
        deployment_internal_id: "build-service-abc123"
        deployment_internal_branch: "main"
        billing_deployment_plan: "nf-compute-50"
        runtime_environment:
          ENVIRONMENT: "production"
          LOG_LEVEL: "info"
```

## Authentication

### API Token Setup

1. Log in to your [Northflank dashboard](https://app.northflank.com)
2. Navigate to **Account Settings > API**
3. Create a new API Role with the following permissions:
   - **Project > General > Read**
   - **Project > Jobs > General** — Create, Read, Delete
4. Create a new API Token using the role you just created
5. Store the token securely using Prefect's block system

```python
from prefect_northflank import Northflank

credentials = Northflank(api_token="nf-...")
credentials.save("my-northflank-creds")
```


## Development

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/northflank/prefect-northflank.git
   cd prefect-northflank
   ```

2. Install with uv:
   ```bash
   uv sync
   uv run python -m pip install -e .
   ```

### Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Support

For support with this integration, please:

1. Check the [documentation](https://github.com/northflank/prefect-northflank)
2. Search existing [issues](https://github.com/northflank/prefect-northflank/issues)
3. Create a new issue if needed

## Links

- [Prefect Documentation](https://docs.prefect.io)
- [Northflank Documentation](https://northflank.com/docs)
- [Northflank API Documentation](https://northflank.com/docs/v1/api)
