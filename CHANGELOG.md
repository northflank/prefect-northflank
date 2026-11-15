# Changelog

## 1.0.2

- Add `deployment_storage_ephemeral_storage_size` to configure runtime ephemeral storage in MB, with a minimum of 1024.
- Add `deployment_storage_shm_size` to configure memory-backed `/dev/shm` in MB, with a minimum of 64.
- Preserve storage settings when the worker selects its default container image.
- Validate storage sizes in both work pool variables and direct Python configuration. Unset sizes retain platform defaults.

Existing work pools must update their base job templates to expose the new variables and configuration mappings. New pools created with this version include them automatically.

Thanks to Zacharias Döhmann for the initial implementation in PR #1.
