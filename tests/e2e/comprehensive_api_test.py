# tests/e2e/comprehensive_api_test.py
"""
Comprehensive API testing with corrected endpoints and detailed reporting.
"""
import httpx
import asyncio
import json
import time

BASE_API_URL = "http://localhost:8000"

async def test_comprehensive_api():
    """Complete API endpoint testing with proper data formats."""
    print("COMPREHENSIVE API TESTING")
    print("=" * 50)

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tests": [],
        "summary": {}
    }

    async with httpx.AsyncClient(timeout=60.0) as client:

        # Test 1: Health Check
        print("1. Health Check...")
        try:
            response = await client.get(f"{BASE_API_URL}/health")
            success = response.status_code == 200 and response.json().get("ok")
            results["tests"].append({
                "name": "Health Check",
                "status": "PASS" if success else "FAIL",
                "response_code": response.status_code,
                "data": response.json() if success else response.text
            })
            print(f"   {'PASS' if success else 'FAIL'}: {response.status_code}")
        except Exception as e:
            results["tests"].append({"name": "Health Check", "status": "ERROR", "error": str(e)})
            print(f"   ERROR: {e}")

        # Test 2: Sources Test
        print("2. Sources Connectivity...")
        try:
            response = await client.get(f"{BASE_API_URL}/sources/test")
            success = response.status_code == 200
            data = response.json() if success else None
            results["tests"].append({
                "name": "Sources Test",
                "status": "PASS" if success else "FAIL",
                "response_code": response.status_code,
                "sources_count": len(data) if data else 0,
                "data": data
            })
            print(f"   {'PASS' if success else 'FAIL'}: {response.status_code}")
            if data:
                print(f"   Sources tested: {len(data)}")
        except Exception as e:
            results["tests"].append({"name": "Sources Test", "status": "ERROR", "error": str(e)})
            print(f"   ERROR: {e}")

        # Test 3: Complete Workflow with LICO
        print("3. Complete Workflow (LICO-based)...")
        try:
            lico_workflow = {
                "lico": {
                    "learner": "university students",
                    "intervention": "instructional design",
                    "context": "online learning environment",
                    "outcome": "learning effectiveness"
                },
                "years": "2020-",
                "sources": ["PubMed", "Crossref", "ERIC"]
            }

            response = await client.post(f"{BASE_API_URL}/run", json=lico_workflow)
            success = response.status_code == 200
            data = response.json() if success else None
            run_id = data.get("run_id") if data else None

            results["tests"].append({
                "name": "LICO Workflow",
                "status": "PASS" if success else "FAIL",
                "response_code": response.status_code,
                "run_id": run_id,
                "data": data
            })

            print(f"   {'PASS' if success else 'FAIL'}: {response.status_code}")
            if run_id:
                print(f"   Run ID: {run_id[:8]}...")

                # Wait and check workflow status
                print("   Monitoring workflow progress...")
                max_wait = 30
                for i in range(max_wait):
                    await asyncio.sleep(2)
                    try:
                        status_response = await client.get(f"{BASE_API_URL}/runs/{run_id}")
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            print(f"   Progress check {i+1}: Status OK")
                            print(f"   Records: {len(status_data.get('records', []))}")
                            print(f"   PRISMA: {status_data.get('prisma', {})}")

                            results["tests"].append({
                                "name": "Workflow Status Check",
                                "status": "PASS",
                                "response_code": status_response.status_code,
                                "records_found": len(status_data.get('records', [])),
                                "prisma_data": status_data.get('prisma', {}),
                                "full_data": status_data
                            })
                            break
                        else:
                            print(f"   Progress check {i+1}: Status {status_response.status_code}")
                    except Exception as e:
                        print(f"   Progress check {i+1}: Error {e}")

        except Exception as e:
            results["tests"].append({"name": "LICO Workflow", "status": "ERROR", "error": str(e)})
            print(f"   ERROR: {e}")

        # Test 4: Simple Query Workflow
        print("4. Simple Query Workflow...")
        try:
            simple_workflow = {
                "query": "machine learning education effectiveness",
                "press": {
                    "concepts": ["machine learning", "education", "effectiveness"],
                    "boolean": '("machine learning"[Title/Abstract]) AND ("education"[Title/Abstract]) AND ("effectiveness"[Title/Abstract])',
                    "sources": ["PubMed", "arXiv"],
                    "years": "2020-",
                    "limits": "English language"
                }
            }

            response = await client.post(f"{BASE_API_URL}/run/press", json=simple_workflow)
            success = response.status_code == 200
            data = response.json() if success else None

            results["tests"].append({
                "name": "Simple Query Workflow",
                "status": "PASS" if success else "FAIL",
                "response_code": response.status_code,
                "data": data
            })

            print(f"   {'PASS' if success else 'FAIL'}: {response.status_code}")

        except Exception as e:
            results["tests"].append({"name": "Simple Query Workflow", "status": "ERROR", "error": str(e)})
            print(f"   ERROR: {e}")

        # Test 5: Export Functionality (if we have a valid run_id)
        if run_id:
            print("5. Export Functionality...")
            try:
                # Test JSON export
                json_response = await client.get(f"{BASE_API_URL}/runs/{run_id}/export/json")
                json_success = json_response.status_code == 200

                # Test CSV export
                csv_response = await client.get(f"{BASE_API_URL}/runs/{run_id}/export/csv")
                csv_success = csv_response.status_code == 200

                results["tests"].append({
                    "name": "Export Functionality",
                    "status": "PASS" if (json_success and csv_success) else "PARTIAL" if (json_success or csv_success) else "FAIL",
                    "json_export": "PASS" if json_success else "FAIL",
                    "csv_export": "PASS" if csv_success else "FAIL",
                    "json_size": len(json_response.content) if json_success else 0,
                    "csv_size": len(csv_response.content) if csv_success else 0
                })

                print(f"   JSON Export: {'PASS' if json_success else 'FAIL'}")
                print(f"   CSV Export: {'PASS' if csv_success else 'FAIL'}")

            except Exception as e:
                results["tests"].append({"name": "Export Functionality", "status": "ERROR", "error": str(e)})
                print(f"   ERROR: {e}")

    # Generate Summary
    total_tests = len(results["tests"])
    passed = len([t for t in results["tests"] if t["status"] == "PASS"])
    failed = len([t for t in results["tests"] if t["status"] in ["FAIL", "ERROR"]])

    results["summary"] = {
        "total_tests": total_tests,
        "passed": passed,
        "failed": failed,
        "success_rate": f"{(passed/total_tests*100):.1f}%" if total_tests > 0 else "0%"
    }

    print("\n" + "=" * 50)
    print("API TEST SUMMARY")
    print("=" * 50)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {results['summary']['success_rate']}")

    # Save detailed results
    with open("tests/api_test_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nDetailed results saved to: tests/api_test_results.json")
    return results

if __name__ == "__main__":
    asyncio.run(test_comprehensive_api())