# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12-slim

LABEL maintainer="Intel Corporation"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY nodes.yaml .

EXPOSE 8080

ENTRYPOINT ["python", "-m", "src"]
CMD ["--config", "nodes.yaml"]
