# Examples

This directory contains example flows and configurations for using Prefect with Northflank.

## Getting Started

1. **Install prefect-northflank**:
   ```bash
   pip install prefect-northflank
   ```

2. **Set up credentials**:
   ```python
   from prefect_northflank import Northflank
   
   credentials = Northflank(api_token="your-api-token")
   credentials.save("northflank-creds")
   ```

3. **Create a work pool**:
   ```bash
   prefect work-pool create --type northflank my-northflank-pool
   ```

4. **Deploy the example**:
   ```bash
   prefect deploy --prefect-file prefect.yaml
   ```

5. **Start a worker**:
   ```bash
   prefect worker start --pool my-northflank-pool
   ```

6. **Run the deployment**:
   ```bash
   prefect deployment run 'hello-northflank/example-deploy'
   ```

## Files

- `example_flow.py` - Basic flow example
- `prefect.yaml` - Deployment configuration
- `advanced_example.py` - Advanced configuration example