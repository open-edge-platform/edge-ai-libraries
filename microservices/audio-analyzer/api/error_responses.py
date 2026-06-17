from fastapi.responses import JSONResponse


def build_openai_error(
    message: str,
    *,
    error_type: str,
    param: str | None = None,
    code: str | None = None,
) -> dict:
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": param,
            "code": code,
        }
    }


def openai_error_response(
    status_code: int,
    message: str,
    *,
    error_type: str | None = None,
    param: str | None = None,
    code: str | None = None,
) -> JSONResponse:
    resolved_type = error_type or ("invalid_request_error" if status_code < 500 else "server_error")
    return JSONResponse(
        status_code=status_code,
        content=build_openai_error(
            message,
            error_type=resolved_type,
            param=param,
            code=code,
        ),
    )