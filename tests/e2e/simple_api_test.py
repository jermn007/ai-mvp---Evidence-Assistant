# tests/e2e/simple_api_test.py
"""
Simple API tests for the literature review application.
Tests core functionality without complex imports.
"""
import httpx
import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

BASE_API_URL = "http://localhost:8000"
BASE_FRONTEND_URL = "http://localhost:5173"

async def test_api_endpoints():
    """Test all major API endpoints."""
    print("Testing API Endpoints")
    print("=" * 50)

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Test 1: Health Check
        print("1. Testing health check...")
        try:
            response = await client.get(f"{BASE_API_URL}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            print("   ✓ Health check passed")
        except Exception as e:
            print(f"   ❌ Health check failed: {e}")
            return False

        # Test 2: Sources Test
        print("2. Testing sources connectivity...")
        try:
            response = await client.get(f"{BASE_API_URL}/sources/test")
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✓ Sources test completed: {len(data)} sources tested")
            else:
                print(f"   ⚠️ Sources test returned {response.status_code}")
        except Exception as e:
            print(f"   ❌ Sources test failed: {e}")

        # Test 3: PRESS Plan Generation
        print("3. Testing PRESS plan generation...")
        try:
            lico_data = {
                "lico": {
                    "learner": ["students", "learners"],
                    "intervention": ["instructional design", "teaching method"],
                    "context": ["classroom", "online learning"],
                    "outcome": ["learning effectiveness", "performance"]
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
                print(f"   ✓ PRESS plan generated with {len(data.get('queries', []))} queries")
            else:
                print(f"   ⚠️ PRESS plan generation returned {response.status_code}")

        except Exception as e:
            print(f"   ❌ PRESS plan generation failed: {e}")

        # Test 4: Simple Workflow Execution
        print("4. Testing simple workflow execution...")
        try:
            workflow_data = {
                "query": "instructional design effectiveness",
                "press": {
                    "concepts": ["instructional design", "effectiveness"],
                    "boolean": '("instructional design"[Title/Abstract]) AND (effectiveness[Title/Abstract])',
                    "sources": ["PubMed", "Crossref"],
                    "years": "2020-",
                    "limits": "English language"
                }
            }

            response = await client.post(
                f"{BASE_API_URL}/run",
                json=workflow_data
            )

            if response.status_code == 200:
                data = response.json()
                run_id = data.get("run_id")
                print(f"   ✓ Workflow started with run_id: {run_id}")

                # Wait a moment and check status
                await asyncio.sleep(3)

                status_response = await client.get(f"{BASE_API_URL}/runs/{run_id}")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    print(f"   ✓ Workflow status checked successfully")
                    print(f"   Records found: {len(status_data.get('records', []))}")
                    print(f"   PRISMA counts: {status_data.get('prisma', {})}")
                else:
                    print(f"   ⚠️ Status check returned {status_response.status_code}")

            else:
                print(f"   ⚠️ Workflow execution returned {response.status_code}")
                error_text = response.text[:200] if response.text else "No error details"
                print(f"   Error: {error_text}")

        except Exception as e:
            print(f"   ❌ Workflow execution failed: {e}")

    print("\n🎉 API testing completed!")
    return True

async def test_frontend_accessibility():
    """Test that the frontend is accessible."""
    print("\n🌐 Testing Frontend Accessibility")
    print("=" * 50)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(BASE_FRONTEND_URL)
            if response.status_code == 200:
                print("   ✓ Frontend is accessible")
                print(f"   Response size: {len(response.content)} bytes")

                # Check for React app indicators
                content = response.text
                if 'react' in content.lower() or 'vite' in content.lower():
                    print("   ✓ React application detected")
                else:
                    print("   ⚠️ React application not clearly detected")

            else:
                print(f"   ❌ Frontend returned status {response.status_code}")

        except Exception as e:
            print(f"   ❌ Frontend accessibility test failed: {e}")

def print_playwright_test_plan():
    """Print the Playwright MCP test plan for manual execution."""
    print("\n🎭 Playwright MCP Test Plan")
    print("=" * 50)
    print("Execute these commands manually with Playwright MCP:")
    print()

    commands = [
        f"Use playwright mcp to navigate to {BASE_FRONTEND_URL}",
        "Use playwright mcp to take screenshot of homepage",
        "Use playwright mcp to fill LICO form with test data",
        "Use playwright mcp to click 'Generate PRESS Plan' button",
        "Use playwright mcp to verify search strategy appears",
        "Use playwright mcp to click 'Execute Workflow' button",
        "Use playwright mcp to monitor workflow progress",
        "Use playwright mcp to verify results are displayed",
        "Use playwright mcp to test CSV export download",
        "Use playwright mcp to test JSON export download"
    ]

    for i, cmd in enumerate(commands, 1):
        print(f"{i:2d}. {cmd}")

    print(f"\nTest data for LICO form:")
    print(f"  Learner: university students")
    print(f"  Intervention: instructional design")
    print(f"  Context: online learning environment")
    print(f"  Outcome: learning effectiveness")
    print(f"  Domain: education")
    print(f"  Year: 2020-")

async def main():
    """Run all tests."""
    print("Literature Review Application E2E Testing")
    print("=" * 60)

    # Run API tests
    await test_api_endpoints()

    # Run frontend tests
    await test_frontend_accessibility()

    # Print Playwright test plan
    print_playwright_test_plan()

    print("\n" + "=" * 60)
    print("✅ E2E Test Suite Setup Complete!")
    print("📋 Next Steps:")
    print("   1. Run Playwright MCP commands manually for UI testing")
    print("   2. Review test results and fix any issues")
    print("   3. Set up CI/CD pipeline for automated testing")
    print("   4. Implement performance benchmarking")

if __name__ == "__main__":
    asyncio.run(main())