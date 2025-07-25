import os
from fastapi import HTTPException
from pydantic import BaseModel
import subprocess

class CompressionRequest(BaseModel):
    model_name: str
    weight_format: str
    hf_token: str | None = None
    model_path: str

def vlm_compress_model(req: CompressionRequest):
    try:
        result = subprocess.run(
            [
            "bash",
            os.path.join(os.path.dirname(__file__), "../scripts/vlm_compress_model.sh"),
            req.model_name,
            req.weight_format,
            req.hf_token if req.hf_token is not None else "",
            req.model_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=True
        )
        print(result.stdout)
        return {"status": "success", "output": result.stdout}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr)
