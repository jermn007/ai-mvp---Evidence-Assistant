# tests/e2e/test_workflow_e2e.py
"""
End-to-end tests for the 5-step literature review workflow.
Uses Playwright MCP for browser automation and API testing.
"""
import pytest
import httpx
import asyncio
import json
import time
from pathlib import Path

# Import test configuration and fixtures
from tests.config.test_env import setup_test_env, cleanup_test_db, TEST_ENV
from tests.fixtures.test_data import (
    SAMPLE_PRESS_PLAN, SAMPLE_LICO, SAMPLE_QUERY,
    MOCK_SEARCH_RESULTS, EXPECTED_PRISMA_COUNTS
)

# Base URLs for testing
BASE_API_URL = "http://localhost:8000"
BASE_FRONTEND_URL = "http://localhost:5173"

class TestWorkflowE2E:
    """End-to-end tests for the complete literature review workflow."""

    @classmethod
    def setup_class(cls):
        """Set up test environment before running tests."""
        setup_test_env()
        cleanup_test_db()

    @classmethod
    def teardown_class(cls):
        """Clean up after all tests complete."""
        cleanup_test_db()

    async def test_api_health_check(self):
        """Test that the FastAPI server is running and healthy."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_API_URL}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True

    async def test_press_planning_workflow(self):
        """Test the PRESS planning step of the workflow."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Test PRESS plan generation from LICO
            payload = {
                "lico": SAMPLE_LICO,
                "domain": "education",
                "year_min": "2020"
            }

            response = await client.post(
                f"{BASE_API_URL}/press/plan/queries",
                json=payload
            )

            assert response.status_code == 200
            data = response.json()
            assert "queries" in data
            assert "strategy" in data
            assert len(data["queries"]) > 0

    async def test_complete_workflow_execution(self):
        """Test the complete 5-step workflow execution."""
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Execute complete workflow with PRESS plan
            payload = {
                "query": SAMPLE_QUERY,
                "press": SAMPLE_PRESS_PLAN.dict()
            }

            response = await client.post(
                f"{BASE_API_URL}/run/press",
                json=payload
            )

            assert response.status_code == 200
            data = response.json()

            # Verify workflow completion
            assert "run_id" in data
            assert "status" in data
            run_id = data["run_id"]

            # Wait for workflow to complete (with timeout)
            max_wait = 60  # seconds
            wait_time = 0
            while wait_time < max_wait:
                status_response = await client.get(f"{BASE_API_URL}/runs/{run_id}/status")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    if status_data.get("status") == "completed":
                        break

                await asyncio.sleep(2)
                wait_time += 2

            # Verify final results
            results_response = await client.get(f"{BASE_API_URL}/runs/{run_id}")
            assert results_response.status_code == 200

            results = results_response.json()
            assert "records" in results
            assert "prisma" in results
            assert "appraisals" in results

    async def test_data_export_functionality(self):
        """Test CSV and JSON export functionality."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # First, run a workflow to get data
            payload = {
                "query": SAMPLE_QUERY,
                "press": SAMPLE_PRESS_PLAN.dict()
            }

            response = await client.post(f"{BASE_API_URL}/run", json=payload)
            assert response.status_code == 200
            run_id = response.json()["run_id"]

            # Wait a moment for processing
            await asyncio.sleep(5)

            # Test JSON export
            json_response = await client.get(f"{BASE_API_URL}/runs/{run_id}/export/json")
            assert json_response.status_code == 200
            assert json_response.headers["content-type"] == "application/json"

            # Test CSV export
            csv_response = await client.get(f"{BASE_API_URL}/runs/{run_id}/export/csv")
            assert csv_response.status_code == 200
            assert "text/csv" in csv_response.headers["content-type"]

    async def test_error_handling(self):
        """Test error handling for invalid requests."""
        async with httpx.AsyncClient() as client:
            # Test invalid run ID
            response = await client.get(f"{BASE_API_URL}/runs/invalid-id")
            assert response.status_code == 404

            # Test malformed PRESS plan
            invalid_payload = {
                "query": "test",
                "press": {"invalid": "plan"}
            }

            response = await client.post(f"{BASE_API_URL}/run/press", json=invalid_payload)
            assert response.status_code in [400, 422]  # Bad request or validation error

# Pytest configuration for async tests
@pytest.mark.asyncio
async def test_api_health():
    """Standalone test for API health check."""
    test_instance = TestWorkflowE2E()
    await test_instance.test_api_health_check()

@pytest.mark.asyncio
async def test_press_planning():
    """Standalone test for PRESS planning."""
    test_instance = TestWorkflowE2E()
    await test_instance.test_press_planning_workflow()

@pytest.mark.asyncio
async def test_complete_workflow():
    """Standalone test for complete workflow."""
    test_instance = TestWorkflowE2E()
    await test_instance.test_complete_workflow_execution()

@pytest.mark.asyncio
async def test_export_functionality():
    """Standalone test for export functionality."""
    test_instance = TestWorkflowE2E()
    await test_instance.test_data_export_functionality()

@pytest.mark.asyncio
async def test_error_handling():
    """Standalone test for error handling."""
    test_instance = TestWorkflowE2E()
    await test_instance.test_error_handling()

if __name__ == "__main__":
    # Run tests directly
    import asyncio

    async def run_all_tests():
        test_instance = TestWorkflowE2E()
        test_instance.setup_class()

        try:
            print("Running API health check...")
            await test_instance.test_api_health_check()
            print("✓ API health check passed")

            print("Running PRESS planning test...")
            await test_instance.test_press_planning_workflow()
            print("✓ PRESS planning test passed")

            print("Running complete workflow test...")
            await test_instance.test_complete_workflow_execution()
            print("✓ Complete workflow test passed")

            print("Running export functionality test...")
            await test_instance.test_data_export_functionality()
            print("✓ Export functionality test passed")

            print("Running error handling test...")
            await test_instance.test_error_handling()
            print("✓ Error handling test passed")

            print("\n🎉 All E2E tests passed!")

        except Exception as e:
            print(f"❌ Test failed: {e}")
            raise
        finally:
            test_instance.teardown_class()

    # Run the tests
    asyncio.run(run_all_tests())