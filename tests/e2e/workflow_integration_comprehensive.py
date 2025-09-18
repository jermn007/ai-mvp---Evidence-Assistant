"""
Comprehensive Workflow Integration Testing
Tests the complete 5-step literature review process: PRESS -> harvest -> dedupe -> appraise -> report
"""
import asyncio
import json
import time
from typing import Dict, List, Any, Optional
import httpx

# Test Configuration
BASE_API_URL = "http://localhost:8000"
TIMEOUT = 300.0  # Extended timeout for complete workflows

class WorkflowIntegrationTestSuite:
    """Complete workflow integration testing suite."""

    def __init__(self):
        self.results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test_type": "workflow_integration",
            "base_url": BASE_API_URL,
            "workflows": [],
            "summary": {}
        }
        self.client = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    def log_workflow(self, workflow_name: str, result: Dict[str, Any]):
        """Log workflow test result."""
        result["workflow_name"] = workflow_name
        result["timestamp"] = time.strftime("%H:%M:%S")
        self.results["workflows"].append(result)

        status = result.get("overall_status", "UNKNOWN")
        print(f"\\n[{status}] {workflow_name}")

        # Print step-by-step results
        if "steps" in result:
            for step in result["steps"]:
                step_status = step.get("status", "UNKNOWN")
                step_name = step.get("step", "Unknown Step")
                print(f"   [{step_status}] {step_name}")
                if step_status == "FAIL" and "error" in step:
                    print(f"      Error: {step['error']}")

    async def test_complete_lico_workflow(self):
        """Test complete workflow using LICO framework."""
        print("\\n1. COMPLETE LICO-BASED WORKFLOW")
        print("=" * 50)

        workflow_result = {
            "steps": [],
            "overall_status": "UNKNOWN",
            "duration_seconds": 0,
            "data_collected": {}
        }

        start_time = time.time()

        try:
            # Step 1: PRESS Planning
            print("   Step 1: PRESS Planning...")
            lico_data = {
                "learner": "medical students",
                "intervention": "virtual reality simulation",
                "context": "surgical skills training",
                "outcome": "technical competency scores"
            }

            press_request = {
                "lico": lico_data,
                "template": "education",
                "use_stock": True,
                "enable_ai": True
            }

            press_response = await self.client.post(f"{BASE_API_URL}/press/plan", json=press_request)
            press_success = press_response.status_code == 200
            press_data = press_response.json() if press_success else None

            workflow_result["steps"].append({
                "step": "PRESS Planning",
                "status": "PASS" if press_success else "FAIL",
                "response_code": press_response.status_code,
                "has_strategies": bool(press_data and press_data.get("strategies")),
                "has_checklist": bool(press_data and press_data.get("checklist")),
                "data": press_data
            })

            if not press_success:
                raise Exception(f"PRESS planning failed: {press_response.status_code}")

            # Step 2: Query Generation
            print("   Step 2: Query Generation...")
            query_request = {"plan": press_data}
            query_response = await self.client.post(f"{BASE_API_URL}/press/plan/queries", json=query_request)
            query_success = query_response.status_code == 200
            query_data = query_response.json() if query_success else None

            workflow_result["steps"].append({
                "step": "Query Generation",
                "status": "PASS" if query_success else "FAIL",
                "response_code": query_response.status_code,
                "has_pubmed_query": bool(query_data and query_data.get("query_pubmed")),
                "has_generic_query": bool(query_data and query_data.get("query_generic")),
                "data": query_data
            })

            if not query_success:
                raise Exception(f"Query generation failed: {query_response.status_code}")

            # Step 3: Complete Workflow Execution
            print("   Step 3: Workflow Execution (Harvest -> Dedupe -> Appraise -> Report)...")
            workflow_request = {
                "plan": press_data,
                "sources": ["PubMed", "ERIC", "arXiv"]  # Limited sources for faster testing
            }

            workflow_response = await self.client.post(f"{BASE_API_URL}/run/press", json=workflow_request)
            workflow_success = workflow_response.status_code == 200
            workflow_data = workflow_response.json() if workflow_success else None
            run_id = workflow_data.get("run_id") if workflow_data else None

            workflow_result["steps"].append({
                "step": "Workflow Execution",
                "status": "PASS" if workflow_success and run_id else "FAIL",
                "response_code": workflow_response.status_code,
                "run_id": run_id,
                "has_prisma": bool(workflow_data and workflow_data.get("prisma")),
                "n_appraised": workflow_data.get("n_appraised", 0) if workflow_data else 0,
                "data": workflow_data
            })

            if not workflow_success or not run_id:
                raise Exception(f"Workflow execution failed: {workflow_response.status_code}")

            # Step 4: Results Validation
            print("   Step 4: Results Validation...")
            await asyncio.sleep(3)  # Allow workflow to complete

            summary_response = await self.client.get(f"{BASE_API_URL}/runs/{run_id}/summary.json")
            summary_success = summary_response.status_code == 200
            summary_data = summary_response.json() if summary_success else None

            n_records = summary_data.get("n_records", 0) if summary_data else 0
            n_appraisals = summary_data.get("n_appraisals", 0) if summary_data else 0
            has_prisma_counts = bool(summary_data and summary_data.get("counts"))

            workflow_result["steps"].append({
                "step": "Results Validation",
                "status": "PASS" if summary_success and n_records > 0 else "FAIL",
                "response_code": summary_response.status_code,
                "n_records": n_records,
                "n_appraisals": n_appraisals,
                "has_prisma_counts": has_prisma_counts,
                "data": summary_data
            })

            # Step 5: Export Validation
            print("   Step 5: Export Validation...")
            export_tests = [
                ("records.json", "Records JSON"),
                ("appraisals.json", "Appraisals JSON"),
                ("prisma.summary.json", "PRISMA Summary")
            ]

            export_results = {}
            for endpoint, name in export_tests:
                try:
                    export_response = await self.client.get(f"{BASE_API_URL}/runs/{run_id}/{endpoint}")
                    export_results[name] = {
                        "success": export_response.status_code == 200,
                        "size_bytes": len(export_response.content)
                    }
                except Exception as e:
                    export_results[name] = {"success": False, "error": str(e)}

            export_success_count = sum(1 for r in export_results.values() if r.get("success"))

            workflow_result["steps"].append({
                "step": "Export Validation",
                "status": "PASS" if export_success_count >= 2 else "FAIL",
                "exports_tested": len(export_tests),
                "exports_successful": export_success_count,
                "export_details": export_results
            })

            # Calculate overall status
            all_steps_passed = all(step["status"] == "PASS" for step in workflow_result["steps"])
            workflow_result["overall_status"] = "PASS" if all_steps_passed else "FAIL"

            # Store collected data
            workflow_result["data_collected"] = {
                "run_id": run_id,
                "lico_used": lico_data,
                "press_plan": press_data,
                "queries_generated": query_data,
                "final_summary": summary_data,
                "export_validation": export_results
            }

        except Exception as e:
            workflow_result["overall_status"] = "ERROR"
            workflow_result["error"] = str(e)
            print(f"   Workflow failed with error: {e}")

        workflow_result["duration_seconds"] = time.time() - start_time
        self.log_workflow("Complete LICO-based Workflow", workflow_result)
        return run_id if workflow_result["overall_status"] == "PASS" else None

    async def test_simple_query_workflow(self):
        """Test workflow with simple text query."""
        print("\\n2. SIMPLE QUERY WORKFLOW")
        print("=" * 50)

        workflow_result = {
            "steps": [],
            "overall_status": "UNKNOWN",
            "duration_seconds": 0
        }

        start_time = time.time()

        try:
            # Execute simple query workflow
            simple_request = {
                "query": "machine learning in medical education effectiveness",
                "years": "2022-",
                "sources": ["PubMed", "arXiv"]
            }

            response = await self.client.post(f"{BASE_API_URL}/run", json=simple_request)
            success = response.status_code == 200
            data = response.json() if success else None
            run_id = data.get("run_id") if data else None

            workflow_result["steps"].append({
                "step": "Simple Query Execution",
                "status": "PASS" if success and run_id else "FAIL",
                "response_code": response.status_code,
                "run_id": run_id,
                "has_prisma": bool(data and data.get("prisma")),
                "data": data
            })

            if success and run_id:
                # Validate results
                await asyncio.sleep(3)
                summary_response = await self.client.get(f"{BASE_API_URL}/runs/{run_id}/summary.json")
                summary_success = summary_response.status_code == 200
                summary_data = summary_response.json() if summary_success else None

                workflow_result["steps"].append({
                    "step": "Results Validation",
                    "status": "PASS" if summary_success else "FAIL",
                    "response_code": summary_response.status_code,
                    "n_records": summary_data.get("n_records", 0) if summary_data else 0,
                    "data": summary_data
                })

            all_steps_passed = all(step["status"] == "PASS" for step in workflow_result["steps"])
            workflow_result["overall_status"] = "PASS" if all_steps_passed else "FAIL"

        except Exception as e:
            workflow_result["overall_status"] = "ERROR"
            workflow_result["error"] = str(e)

        workflow_result["duration_seconds"] = time.time() - start_time
        self.log_workflow("Simple Query Workflow", workflow_result)

    async def test_workflow_with_ai_enhancement(self):
        """Test workflow with AI-enhanced PRESS planning."""
        print("\\n3. AI-ENHANCED WORKFLOW")
        print("=" * 50)

        workflow_result = {
            "steps": [],
            "overall_status": "UNKNOWN",
            "duration_seconds": 0
        }

        start_time = time.time()

        try:
            # Check AI availability first
            ai_status_response = await self.client.get(f"{BASE_API_URL}/ai/status")
            ai_available = (ai_status_response.status_code == 200 and
                          ai_status_response.json().get("available", False))

            if not ai_available:
                workflow_result["overall_status"] = "SKIPPED"
                workflow_result["reason"] = "AI service not available"
                self.log_workflow("AI-Enhanced Workflow", workflow_result)
                return

            # Test AI-enhanced PRESS planning
            lico_data = {
                "learner": "pharmacy students",
                "intervention": "case-based learning",
                "context": "clinical pharmacy education",
                "outcome": "problem-solving skills"
            }

            ai_press_request = {
                "lico": lico_data,
                "template": "education",
                "use_stock": True,
                "enable_ai": True,
                "research_domain": "pharmacy education"
            }

            response = await self.client.post(f"{BASE_API_URL}/press/plan/ai-enhanced", json=ai_press_request)
            success = response.status_code == 200
            data = response.json() if success else None

            has_base_plan = bool(data and data.get("base_plan"))
            has_ai_enhancement = bool(data and data.get("ai_enhancement"))
            has_strategy_analysis = bool(data and data.get("strategy_analysis"))

            workflow_result["steps"].append({
                "step": "AI-Enhanced PRESS Planning",
                "status": "PASS" if success and has_base_plan else "FAIL",
                "response_code": response.status_code,
                "has_base_plan": has_base_plan,
                "has_ai_enhancement": has_ai_enhancement,
                "has_strategy_analysis": has_strategy_analysis,
                "ai_available": data.get("ai_available", False) if data else False,
                "data": data
            })

            # Test AI LICO enhancement separately
            lico_enhancement_request = {
                "lico": lico_data,
                "research_domain": "pharmacy education"
            }

            lico_response = await self.client.post(f"{BASE_API_URL}/ai/enhance-lico", json=lico_enhancement_request)
            lico_success = lico_response.status_code == 200

            workflow_result["steps"].append({
                "step": "LICO AI Enhancement",
                "status": "PASS" if lico_success else "FAIL",
                "response_code": lico_response.status_code,
                "data": lico_response.json() if lico_success else None
            })

            all_steps_passed = all(step["status"] == "PASS" for step in workflow_result["steps"])
            workflow_result["overall_status"] = "PASS" if all_steps_passed else "FAIL"

        except Exception as e:
            workflow_result["overall_status"] = "ERROR"
            workflow_result["error"] = str(e)

        workflow_result["duration_seconds"] = time.time() - start_time
        self.log_workflow("AI-Enhanced Workflow", workflow_result)

    async def test_workflow_error_handling(self):
        """Test workflow error handling and validation."""
        print("\\n4. WORKFLOW ERROR HANDLING")
        print("=" * 50)

        workflow_result = {
            "steps": [],
            "overall_status": "UNKNOWN",
            "duration_seconds": 0
        }

        start_time = time.time()

        try:
            # Test invalid LICO data
            invalid_request = {
                "lico": {
                    "learner": "",  # Empty learner
                    "intervention": "test",
                    "context": "test",
                    "outcome": "test"
                }
            }

            response = await self.client.post(f"{BASE_API_URL}/press/plan", json=invalid_request)
            # Should either succeed with empty learner or fail gracefully
            handled_gracefully = response.status_code in [200, 400, 422]

            workflow_result["steps"].append({
                "step": "Invalid LICO Handling",
                "status": "PASS" if handled_gracefully else "FAIL",
                "response_code": response.status_code,
                "handled_gracefully": handled_gracefully
            })

            # Test malformed request
            try:
                malformed_response = await self.client.post(f"{BASE_API_URL}/run", json={"invalid": "data"})
                # Accept any error status code as valid error handling
                malformed_handled = malformed_response.status_code >= 400

                workflow_result["steps"].append({
                    "step": "Malformed Request Handling",
                    "status": "PASS" if malformed_handled else "FAIL",
                    "response_code": malformed_response.status_code,
                    "handled_gracefully": malformed_handled
                })
            except Exception as e:
                # Exception during malformed request is acceptable
                workflow_result["steps"].append({
                    "step": "Malformed Request Handling",
                    "status": "PASS",
                    "note": f"Exception thrown as expected: {str(e)}"
                })

            # Test non-existent run ID
            fake_run_response = await self.client.get(f"{BASE_API_URL}/runs/fake-run-id-12345/summary.json")
            # Accept 404 or any 4xx error as valid handling
            fake_run_handled = fake_run_response.status_code in [404, 400, 422] or fake_run_response.status_code >= 400

            workflow_result["steps"].append({
                "step": "Non-existent Run ID Handling",
                "status": "PASS" if fake_run_handled else "FAIL",
                "response_code": fake_run_response.status_code,
                "returned_404": fake_run_response.status_code == 404,
                "handled_gracefully": fake_run_handled
            })

            all_steps_passed = all(step["status"] == "PASS" for step in workflow_result["steps"])
            workflow_result["overall_status"] = "PASS" if all_steps_passed else "FAIL"

        except Exception as e:
            workflow_result["overall_status"] = "ERROR"
            workflow_result["error"] = str(e)

        workflow_result["duration_seconds"] = time.time() - start_time
        self.log_workflow("Workflow Error Handling", workflow_result)

    async def test_workflow_performance(self, run_id: Optional[str] = None):
        """Test workflow performance and response times."""
        print("\\n5. WORKFLOW PERFORMANCE TESTING")
        print("=" * 50)

        workflow_result = {
            "steps": [],
            "overall_status": "UNKNOWN",
            "duration_seconds": 0,
            "performance_metrics": {}
        }

        start_time = time.time()

        try:
            # Test API response times
            endpoints_to_test = [
                ("/health", "Health Check"),
                ("/sources/test?max_n=1", "Sources Test"),
                ("/ai/status", "AI Status")
            ]

            if run_id:
                endpoints_to_test.extend([
                    (f"/runs/{run_id}/summary.json", "Run Summary"),
                    (f"/runs/{run_id}/records.json", "Records Export")
                ])

            response_times = {}
            for endpoint, name in endpoints_to_test:
                endpoint_start = time.time()
                try:
                    response = await self.client.get(f"{BASE_API_URL}{endpoint}")
                    response_time = (time.time() - endpoint_start) * 1000  # Convert to ms
                    response_times[name] = {
                        "response_time_ms": response_time,
                        "status_code": response.status_code,
                        "success": response.status_code == 200
                    }
                except Exception as e:
                    response_times[name] = {
                        "response_time_ms": -1,
                        "error": str(e),
                        "success": False
                    }

            # Performance criteria
            fast_responses = sum(1 for r in response_times.values()
                               if r.get("response_time_ms", float('inf')) < 1000 and r.get("success"))
            successful_responses = sum(1 for r in response_times.values() if r.get("success"))

            workflow_result["steps"].append({
                "step": "Response Time Testing",
                "status": "PASS" if successful_responses >= len(endpoints_to_test) * 0.8 else "FAIL",
                "endpoints_tested": len(endpoints_to_test),
                "successful_responses": successful_responses,
                "fast_responses_under_1s": fast_responses,
                "response_times": response_times
            })

            workflow_result["performance_metrics"] = response_times
            workflow_result["overall_status"] = "PASS" if successful_responses >= len(endpoints_to_test) * 0.8 else "FAIL"

        except Exception as e:
            workflow_result["overall_status"] = "ERROR"
            workflow_result["error"] = str(e)

        workflow_result["duration_seconds"] = time.time() - start_time
        self.log_workflow("Workflow Performance Testing", workflow_result)

    def generate_summary(self):
        """Generate comprehensive workflow test summary."""
        total_workflows = len(self.results["workflows"])
        passed_workflows = len([w for w in self.results["workflows"] if w.get("overall_status") == "PASS"])
        failed_workflows = len([w for w in self.results["workflows"] if w.get("overall_status") == "FAIL"])
        error_workflows = len([w for w in self.results["workflows"] if w.get("overall_status") == "ERROR"])
        skipped_workflows = len([w for w in self.results["workflows"] if w.get("overall_status") == "SKIPPED"])

        success_rate = (passed_workflows / total_workflows * 100) if total_workflows > 0 else 0

        self.results["summary"] = {
            "total_workflows": total_workflows,
            "passed": passed_workflows,
            "failed": failed_workflows,
            "errors": error_workflows,
            "skipped": skipped_workflows,
            "success_rate": f"{success_rate:.1f}%",
            "total_duration": sum(w.get("duration_seconds", 0) for w in self.results["workflows"])
        }

        print("\\n" + "=" * 60)
        print("WORKFLOW INTEGRATION TEST SUMMARY")
        print("=" * 60)
        print(f"Total Workflows: {total_workflows}")
        print(f"Passed: {passed_workflows}")
        print(f"Failed: {failed_workflows}")
        print(f"Errors: {error_workflows}")
        print(f"Skipped: {skipped_workflows}")
        print(f"Success Rate: {success_rate:.1f}%")
        print(f"Total Duration: {self.results['summary']['total_duration']:.1f}s")

    async def run_all_tests(self):
        """Execute complete workflow integration test suite."""
        print("EVIDENCE ASSISTANT - WORKFLOW INTEGRATION TESTING")
        print("=" * 60)
        print(f"Target: {BASE_API_URL}")
        print(f"Started: {self.results['timestamp']}")

        # Execute workflow tests
        run_id = await self.test_complete_lico_workflow()
        await self.test_simple_query_workflow()
        await self.test_workflow_with_ai_enhancement()
        await self.test_workflow_error_handling()
        await self.test_workflow_performance(run_id)

        # Generate final summary
        self.generate_summary()

        # Save detailed results
        output_file = "tests/workflow_integration_test_results.json"
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\\nDetailed results saved to: {output_file}")
        return self.results

async def main():
    """Main test execution function."""
    async with WorkflowIntegrationTestSuite() as test_suite:
        return await test_suite.run_all_tests()

if __name__ == "__main__":
    results = asyncio.run(main())