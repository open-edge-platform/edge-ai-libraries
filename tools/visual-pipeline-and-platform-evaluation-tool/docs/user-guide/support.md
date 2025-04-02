# Get Help

This page provides troubleshooting steps, FAQs, and resources to help you resolve common issues.


## Troubleshooting Common Issues
### 1. Containers Not Starting
- **Issue**: The application containers fail to start.
- **Solution**:

  ```bash
  docker compose logs
  ```
  Check the logs for errors and resolve dependency issues.

### 2. Port Conflicts
- **Issue**: Port conflicts with other running applications.
- **Solution**: Update the ports section in the Docker Compose file.
