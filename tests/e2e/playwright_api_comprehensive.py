"""
Comprehensive API Testing using Playwright MCP for Evidence Assistant
Tests all documented API endpoints with enhanced validation and reporting.
"""
import asyncio
import json
import time
from typing import Dict, List, Any
import httpx

# Test Configuration
BASE_API_URL = "http://localhost:8000"
TIMEOUT = 120.0  # Extended timeout for complex workflows

class APITestSuite:
    """Comprehensive API testing suite using httpx for direct API calls."""

    def __init__(self):
        self.results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "environment": "local",
            "base_url": BASE_API_URL,
            "test_categories": {},
            "summary": {}
        }
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def log_test(self, category: str, test_name: str, result: Dict[str, Any]):
        """Log test result to structured output."""
        if category not in self.results["test_categories"]:
            self.results["test_categories"][category] = []

        result["test_name"] = test_name
        result["timestamp"] = time.strftime("%H:%M:%S")
        self.results["test_categories"][category].append(result)

        status = result.get("status", "UNKNOWN")
        print(f"   [{status}] {test_name}")
        if status == "FAIL" and "error" in result:
            print(f"      Error: {result['error']}")

    async def test_health_endpoints(self):
        """Test system health and status endpoints."""
        print("\n1. HEALTH & STATUS ENDPOINTS")
        print("-" * 40)

        # Test /health
        try:
            response = await self.client.get(f"{BASE_API_URL}/health")
            data = response.json() if response.status_code == 200 else None

            self.log_test("health", "Basic Health Check", {
                "status": "PASS" if response.status_code == 200 and data.get("ok") else "FAIL",
                "response_code": response.status_code,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "data": data,
                "checks": {
                    "status_ok": response.status_code == 200,
                    "response_ok": data.get("ok") if data else False,
                    "env_configured": data.get("env") if data else False
                }
            })
        except Exception as e:
            self.log_test("health", "Basic Health Check", {
                "status": "ERROR", "error": str(e)
            })

        # Test /health/checkpointer
        try:
            response = await self.client.get(f"{BASE_API_URL}/health/checkpointer")
            data = response.json() if response.status_code == 200 else None

            self.log_test("health", "Checkpointer Status", {
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "response_code": response.status_code,
                "checkpointer_type": data.get("checkpointer") if data else None,
                "data": data
            })
        except Exception as e:
            self.log_test("health", "Checkpointer Status", {
                "status": "ERROR", "error": str(e)
            })

    async def test_sources_endpoints(self):
        """Test academic source connectivity."""
        print("\n2. ACADEMIC SOURCES ENDPOINTS")
        print("-" * 40)

        # Test source connectivity
        try:
            response = await self.client.get(f"{BASE_API_URL}/sources/test?max_n=3")
            data = response.json() if response.status_code == 200 else None

            source_results = {}
            if data and "sources" in data:
                for source, info in data["sources"].items():
                    source_results[source] = {
                        "available": "error" not in info,
                        "count": info.get("count", 0),
                        "error": info.get("error")
                    }

            self.log_test("sources", "Academic Database Connectivity", {
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "response_code": response.status_code,
                "sources_tested": len(source_results),
                "sources_available": len([s for s in source_results.values() if s["available"]]),
                "source_details": source_results,
                "data": data
            })
        except Exception as e:
            self.log_test("sources", "Academic Database Connectivity", {
                "status": "ERROR", "error": str(e)
            })

    async def test_press_planning_endpoints(self):
        """Test PRESS planning and strategy generation."""
        print("\n3. PRESS PLANNING ENDPOINTS")
        print("-" * 40)

        # Test data for PRESS planning
        test_lico = {
            "learner": "medical students",
            "intervention": "simulation-based learning",
            "context": "clinical skills training",
            "outcome": "competency assessment scores"
        }

        # Test PRESS plan generation
        try:
            press_request = {
                "lico": test_lico,
                "template": "education",
                "use_stock": True,
                "enable_ai": False
            }

            response = await self.client.post(f"{BASE_API_URL}/press/plan", json=press_request)
            data = response.json() if response.status_code == 200 else None

            plan_valid = False
            if data:
                plan_valid = (
                    "question_lico" in data and
                    "strategies" in data and
                    "checklist" in data
                )

            self.log_test("press", "PRESS Plan Generation", {
                "status": "PASS" if response.status_code == 200 and plan_valid else "FAIL",
                "response_code": response.status_code,
                "plan_structure_valid": plan_valid,
                "has_strategies": bool(data and data.get("strategies")),
                "strategy_count": len(data.get("strategies", {})) if data else 0,
                "data": data
            })

            # If plan generation succeeded, test query extraction
            if response.status_code == 200 and data:
                try:
                    query_response = await self.client.post(
                        f"{BASE_API_URL}/press/plan/queries",
                        json={"plan": data}
                    )
                    query_data = query_response.json() if query_response.status_code == 200 else None

                    self.log_test("press", "Query Extraction from Plan", {
                        "status": "PASS" if query_response.status_code == 200 else "FAIL",
                        "response_code": query_response.status_code,
                        "has_pubmed_query": bool(query_data and query_data.get("query_pubmed")),
                        "has_generic_query": bool(query_data and query_data.get("query_generic")),
                        "data": query_data
                    })
                except Exception as e:
                    self.log_test("press", "Query Extraction from Plan", {
                        "status": "ERROR", "error": str(e)
                    })

        except Exception as e:
            self.log_test("press", "PRESS Plan Generation", {
                "status": "ERROR", "error": str(e)
            })

    async def test_ai_endpoints(self):
        """Test AI-powered research assistance endpoints."""
        print("\n4. AI RESEARCH ASSISTANCE ENDPOINTS")
        print("-" * 40)

        # Test AI status
        try:
            response = await self.client.get(f"{BASE_API_URL}/ai/status")
            data = response.json() if response.status_code == 200 else None

            self.log_test("ai", "AI Service Status", {
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "response_code": response.status_code,
                "ai_available": data.get("available") if data else False,
                "features_count": len(data.get("features", [])) if data else 0,
                "data": data
            })

            # Only test AI features if service is available
            if data and data.get("available"):
                # Test LICO enhancement
                try:
                    lico_request = {
                        "lico": {
                            "learner": "nursing students",
                            "intervention": "problem-based learning",
                            "context": "undergraduate education",
                            "outcome": "critical thinking"
                        },
                        "research_domain": "healthcare education"
                    }

                    response = await self.client.post(f"{BASE_API_URL}/ai/enhance-lico", json=lico_request)

                    self.log_test("ai", "LICO Enhancement", {
                        "status": "PASS" if response.status_code == 200 else "FAIL",
                        "response_code": response.status_code,
                        "data": response.json() if response.status_code == 200 else None
                    })
                except Exception as e:
                    self.log_test("ai", "LICO Enhancement", {
                        "status": "ERROR", "error": str(e)
                    })

                # Test research question generation
                try:
                    question_request = {
                        "lico": {
                            "learner": "medical students",
                            "intervention": "virtual reality",
                            "context": "anatomy education",
                            "outcome": "learning retention"
                        }
                    }

                    response = await self.client.post(f"{BASE_API_URL}/ai/generate-question", json=question_request)

                    self.log_test("ai", "Research Question Generation", {
                        "status": "PASS" if response.status_code == 200 else "FAIL",
                        "response_code": response.status_code,
                        "has_question": bool(response.status_code == 200 and response.json().get("question")),
                        "data": response.json() if response.status_code == 200 else None
                    })
                except Exception as e:
                    self.log_test("ai", "Research Question Generation", {
                        "status": "ERROR", "error": str(e)
                    })

        except Exception as e:
            self.log_test("ai", "AI Service Status", {
                "status": "ERROR", "error": str(e)
            })

    async def test_workflow_endpoints(self):
        """Test core literature review workflow execution."""
        print("\n5. WORKFLOW EXECUTION ENDPOINTS")
        print("-" * 40)

        # Test basic workflow execution
        try:
            workflow_request = {
                "lico": {
                    "learner": "healthcare professionals",
                    "intervention": "educational technology",
                    "context": "continuing education",
                    "outcome": "knowledge retention"
                },
                "years": "2022-",
                "sources": ["PubMed", "ERIC"]  # Limited sources for faster testing
            }

            response = await self.client.post(f"{BASE_API_URL}/run", json=workflow_request)
            data = response.json() if response.status_code == 200 else None
            run_id = data.get("run_id") if data else None

            self.log_test("workflow", "Basic Workflow Execution", {
                "status": "PASS" if response.status_code == 200 and run_id else "FAIL",
                "response_code": response.status_code,
                "run_id": run_id,
                "has_prisma": bool(data and data.get("prisma")),
                "n_appraised": data.get("n_appraised", 0) if data else 0,
                "data": data
            })

            # If workflow succeeded, test summary retrieval
            if run_id:
                try:
                    # Wait a moment for workflow to process
                    await asyncio.sleep(2)

                    summary_response = await self.client.get(f"{BASE_API_URL}/runs/{run_id}/summary.json")
                    summary_data = summary_response.json() if summary_response.status_code == 200 else None

                    self.log_test("workflow", "Run Summary Retrieval", {
                        "status": "PASS" if summary_response.status_code == 200 else "FAIL",
                        "response_code": summary_response.status_code,
                        "has_run_info": bool(summary_data and summary_data.get("run")),
                        "n_records": summary_data.get("n_records", 0) if summary_data else 0,
                        "n_appraisals": summary_data.get("n_appraisals", 0) if summary_data else 0,
                        "data": summary_data
                    })

                    return run_id  # Return for export testing

                except Exception as e:
                    self.log_test("workflow", "Run Summary Retrieval", {
                        "status": "ERROR", "error": str(e)
                    })

        except Exception as e:
            self.log_test("workflow", "Basic Workflow Execution", {
                "status": "ERROR", "error": str(e)
            })

        return None

    async def test_export_endpoints(self, run_id: str = None):
        """Test data export functionality."""
        print("\n6. DATA EXPORT ENDPOINTS")
        print("-" * 40)

        if not run_id:
            print("   Skipping export tests - no valid run_id available")
            return

        # Test various export formats
        export_tests = [
            ("records.json", "Records JSON Export"),
            ("records.csv", "Records CSV Export"),
            ("appraisals.json", "Appraisals JSON Export"),
            ("appraisals.csv", "Appraisals CSV Export"),
            ("records_with_appraisals.json", "Combined Records+Appraisals JSON"),
            ("prisma.summary.json", "PRISMA Summary JSON")
        ]

        for endpoint, test_name in export_tests:
            try:
                response = await self.client.get(f"{BASE_API_URL}/runs/{run_id}/{endpoint}")

                content_size = len(response.content) if response.content else 0
                is_json = endpoint.endswith('.json')

                # For JSON endpoints, try to parse content
                valid_format = True
                if is_json and response.status_code == 200:
                    try:
                        json.loads(response.content)
                    except json.JSONDecodeError:
                        valid_format = False

                self.log_test("export", test_name, {
                    "status": "PASS" if response.status_code == 200 and valid_format else "FAIL",
                    "response_code": response.status_code,
                    "content_size_bytes": content_size,
                    "valid_format": valid_format,
                    "endpoint": endpoint
                })

            except Exception as e:
                self.log_test("export", test_name, {
                    "status": "ERROR", "error": str(e), "endpoint": endpoint
                })

    async def test_runs_management(self):
        """Test runs listing and management."""
        print("\n7. RUNS MANAGEMENT ENDPOINTS")
        print("-" * 40)

        # Test runs listing
        try:
            response = await self.client.get(f"{BASE_API_URL}/runs.page.json?limit=5")
            data = response.json() if response.status_code == 200 else None

            self.log_test("management", "Runs Listing", {
                "status": "PASS" if response.status_code == 200 else "FAIL",
                "response_code": response.status_code,
                "total_runs": data.get("total", 0) if data else 0,
                "items_returned": len(data.get("items", [])) if data else 0,
                "has_pagination": bool(data and "limit" in data and "offset" in data),
                "data": data
            })

        except Exception as e:
            self.log_test("management", "Runs Listing", {
                "status": "ERROR", "error": str(e)
            })

    def generate_summary(self):
        """Generate comprehensive test summary."""
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        error_tests = 0

        for category, tests in self.results["test_categories"].items():
            for test in tests:
                total_tests += 1
                status = test.get("status", "UNKNOWN")
                if status == "PASS":
                    passed_tests += 1
                elif status == "FAIL":
                    failed_tests += 1
                elif status == "ERROR":
                    error_tests += 1

        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        self.results["summary"] = {
            "total_tests": total_tests,
            "passed": passed_tests,
            "failed": failed_tests,
            "errors": error_tests,
            "success_rate": f"{success_rate:.1f}%",
            "categories_tested": len(self.results["test_categories"]),
            "test_duration_seconds": time.time() - time.mktime(time.strptime(self.results["timestamp"], "%Y-%m-%d %H:%M:%S"))
        }

        print("\n" + "=" * 60)
        print("COMPREHENSIVE API TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Errors: {error_tests}")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Categories: {len(self.results['test_categories'])}")
        print(f"Duration: {self.results['summary']['test_duration_seconds']:.1f}s")

    async def run_all_tests(self):
        """Execute complete test suite."""
        print("EVIDENCE ASSISTANT - COMPREHENSIVE API TESTING")
        print("=" * 60)
        print(f"Target: {BASE_API_URL}")
        print(f"Started: {self.results['timestamp']}")

        # Execute test suites in logical order
        await self.test_health_endpoints()
        await self.test_sources_endpoints()
        await self.test_press_planning_endpoints()
        await self.test_ai_endpoints()

        # Workflow test returns run_id for export testing
        run_id = await self.test_workflow_endpoints()
        await self.test_export_endpoints(run_id)
        await self.test_runs_management()

        # Generate final summary
        self.generate_summary()

        # Save detailed results
        output_file = "tests/playwright_api_test_results.json"
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\nDetailed results saved to: {output_file}")
        return self.results

async def main():
    """Main test execution function."""
    async with APITestSuite() as test_suite:
        return await test_suite.run_all_tests()

if __name__ == "__main__":
    results = asyncio.run(main())