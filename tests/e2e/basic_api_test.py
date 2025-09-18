# tests/e2e/basic_api_test.py
"""
Basic API tests with ASCII output only.
"""
import httpx
import asyncio

BASE_API_URL = "http://localhost:8000"

async def test_basic_endpoints():
    """Test basic API endpoints."""
    print("Testing API Endpoints")
    print("=" * 40)

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Test 1: Health Check
        print("1. Health check...")
        try:
            response = await client.get(f"{BASE_API_URL}/health")
            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    print("   PASS: Health check successful")
                else:
                    print("   FAIL: Health check returned false")
            else:
                print(f"   FAIL: Health check returned {response.status_code}")
        except Exception as e:
            print(f"   ERROR: {e}")

        # Test 2: PRESS Plan Generation
        print("2. PRESS plan generation...")
        try:
            lico_data = {
                "lico": {
                    "learner": ["students"],
                    "intervention": ["instructional design"],
                    "context": ["classroom"],
                    "outcome": ["learning effectiveness"]
                },
                "domain": "education",
                "year_min": "2020"
            }

            response = await client.post(
                f"{BASE_API_URL}/press/plan/queries",
                json=lico_data
            )

            if response.status_code == 200:
                data = response.json()
                query_count = len(data.get('queries', []))
                print(f"   PASS: Generated {query_count} queries")
            else:
                print(f"   FAIL: Returned status {response.status_code}")

        except Exception as e:
            print(f"   ERROR: {e}")

        # Test 3: Simple Workflow
        print("3. Simple workflow execution...")
        try:
            workflow_data = {
                "query": "instructional design",
                "press": {
                    "concepts": ["instructional design"],
                    "boolean": '"instructional design"[Title/Abstract]',
                    "sources": ["PubMed"],
                    "years": "2020-",
                    "limits": "English"
                }
            }

            response = await client.post(
                f"{BASE_API_URL}/run",
                json=workflow_data
            )

            if response.status_code == 200:
                data = response.json()
                run_id = data.get("run_id")
                print(f"   PASS: Workflow started (ID: {run_id[:8]}...)")

                # Brief status check
                await asyncio.sleep(2)
                status_response = await client.get(f"{BASE_API_URL}/runs/{run_id}")
                if status_response.status_code == 200:
                    print("   PASS: Status check successful")
                else:
                    print(f"   WARN: Status check returned {status_response.status_code}")

            else:
                print(f"   FAIL: Workflow returned {response.status_code}")

        except Exception as e:
            print(f"   ERROR: {e}")

    print("\nTesting completed!")

async def main():
    await test_basic_endpoints()

if __name__ == "__main__":
    asyncio.run(main())