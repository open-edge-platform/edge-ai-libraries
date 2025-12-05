# Troubleshooting

This page provides troubleshooting steps, FAQs, and resources to assist in resolving common issues.

## Troubleshooting Common Issues

### 1. Containers Not Starting

- **Issue**: Application containers fail to start.
- **Solution**:

  ```bash
  docker compose logs
  ```

  Logs should be checked for errors and any reported dependency issues should be resolved.

### 2. Port Conflicts

- **Issue**: Port conflicts with other running applications.
- **Solution**: The `ports` section in the Docker Compose file should be updated to use available ports.
