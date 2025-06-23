# Unit test guidelines
IMPORTANT: the microservice MUST be deployed before running the unit tests. Please refer to the [get started guide](../docs/user-guide/get-started.md) to deploy first.

## Test with pytest tool

```
bash run_app_ut.sh
```

## Warning
The vector DB will be cleared during the unit tests. DO NOT run the unit tests in the production environment.