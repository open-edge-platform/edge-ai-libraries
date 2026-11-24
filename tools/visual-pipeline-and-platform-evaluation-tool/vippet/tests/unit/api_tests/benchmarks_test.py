# SPDX-License-Identifier: Apache-2.0
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI

import database
from api.routes.benchmarks import router as benchmarks_router
from orm_models import (
    BenchmarkSuite,
    BenchmarkSuiteRun,
    BenchmarkTestCase,
    BenchmarkTestCaseRun,
    BenchmarkWorkload,
    BenchmarkWorkloadRun,
)

METRICS_JSON = '[{"timestamp": 1, "metrics": [{"name": "cpu", "value": 1}]}]'


class TestBenchmarkRunDetailsAPI(unittest.IsolatedAsyncioTestCase):
    """Unit tests for benchmark run detail endpoints backed by a temp SQLite DB."""

    async def asyncSetUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="vippet-benchmarks-db-")
        self._orig_database_url = database.DATABASE_URL
        database.DATABASE_URL = (
            f"sqlite+aiosqlite:///{os.path.join(self._tmpdir, 'test.db')}"
        )
        self._orig_seed = os.environ.get("DB_SEED_ON_STARTUP")
        os.environ["DB_SEED_ON_STARTUP"] = "false"
        await database.init_db()

        self.test_case_run_id = await self._seed_run()

        app = FastAPI()
        app.include_router(benchmarks_router, prefix="/benchmarks")
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await database.close_db()
        database.DATABASE_URL = self._orig_database_url
        if self._orig_seed is None:
            os.environ.pop("DB_SEED_ON_STARTUP", None)
        else:
            os.environ["DB_SEED_ON_STARTUP"] = self._orig_seed
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _seed_run(self) -> int:
        """Insert one suite run with one completed test case run; return its id."""
        now = datetime.now(timezone.utc)
        assert database.async_session_maker is not None
        async with database.async_session_maker() as session:
            suite = BenchmarkSuite(
                slug="test-suite",
                name="Test Suite",
                description="desc",
                created_at=now,
                last_run_at=now,
            )
            session.add(suite)
            await session.flush()

            workload = BenchmarkWorkload(
                suite_id=suite.id, pipeline_id="pipeline-1", variants="cpu"
            )
            session.add(workload)
            await session.flush()

            test_case = BenchmarkTestCase(
                workload_id=workload.id, variant_id="cpu", streams=1
            )
            suite_run = BenchmarkSuiteRun(
                id=1,
                suite_id=suite.id,
                start_time=1000,
                execution_time=10,
                job_id="suite-job",
                status="completed",
                total_test_cases=1,
                passed_test_cases=1,
            )
            session.add_all([test_case, suite_run])
            await session.flush()

            workload_run = BenchmarkWorkloadRun(
                workload_id=workload.id,
                suite_run_id=suite_run.id,
                start_time=1000,
                execution_time=10,
                status="completed",
            )
            session.add(workload_run)
            await session.flush()

            test_case_run = BenchmarkTestCaseRun(
                test_case_id=test_case.id,
                workload_run_id=workload_run.id,
                start_time=1000,
                execution_time=10,
                total_fps=30.0,
                metrics=METRICS_JSON,
                job_id="test-case-job",
                status="completed",
            )
            session.add(test_case_run)
            await session.commit()
            return test_case_run.id

    async def test_run_details_omit_test_case_metrics(self) -> None:
        response = await self.client.get("/benchmarks/test-suite/run/1")

        self.assertEqual(response.status_code, 200, response.text)
        test_case_runs = response.json()["workload_runs"][0]["test_case_runs"]
        self.assertEqual(len(test_case_runs), 1)
        self.assertEqual(test_case_runs[0]["total_fps"], 30.0)
        self.assertIsNone(test_case_runs[0]["metrics"])

    async def test_test_run_details_include_metrics(self) -> None:
        response = await self.client.get(
            f"/benchmarks/test-suite/run/1/test/{self.test_case_run_id}"
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["metrics"], METRICS_JSON)


if __name__ == "__main__":
    unittest.main()
