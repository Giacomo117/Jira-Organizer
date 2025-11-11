import requests
import sys
import json
from datetime import datetime

class JiraSyncAPITester:
    def __init__(self, base_url="https://jira-sync-2.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        default_headers = {'Content-Type': 'application/json'}
        if headers:
            default_headers.update(headers)

        try:
            if method == 'GET':
                response = requests.get(url, headers=default_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=default_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=default_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=default_headers, timeout=30)

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if not success:
                try:
                    error_data = response.json()
                    details += f", Error: {error_data.get('detail', 'Unknown error')}"
                except:
                    details += f", Response: {response.text[:200]}"

            self.log_test(name, success, details)
            return success, response.json() if success and response.content else {}

        except requests.exceptions.Timeout:
            self.log_test(name, False, "Request timeout")
            return False, {}
        except Exception as e:
            self.log_test(name, False, f"Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test root API endpoint"""
        return self.run_test("Root API Endpoint", "GET", "", 200)

    def test_jira_config_flow(self):
        """Test complete Jira configuration flow"""
        print("\n🔧 Testing Jira Configuration Flow...")
        
        # Test getting config (should be empty initially)
        success, config_data = self.run_test("Get Jira Config (Empty)", "GET", "jira/config", 200)
        
        # Test saving config with test credentials
        test_config = {
            "jira_domain": "test.atlassian.net",
            "jira_email": "test@example.com",
            "jira_api_token": "test_token_123"
        }
        
        success, _ = self.run_test("Save Jira Config", "POST", "jira/config", 200, test_config)
        
        # Test getting config after saving
        success, config_data = self.run_test("Get Jira Config (After Save)", "GET", "jira/config", 200)
        
        # Test connection (will fail with test credentials, but should return proper response)
        success, test_result = self.run_test("Test Jira Connection", "POST", "jira/test-connection", 200)
        
        return success

    def test_analysis_flow(self):
        """Test meeting analysis creation and management"""
        print("\n📊 Testing Analysis Flow...")
        
        # Test creating analysis
        analysis_data = {
            "jira_project_key": "TEST",
            "client_name": "Test Client",
            "project_name": "Test Project",
            "meeting_minutes": "Test meeting minutes:\n- Discussed new feature implementation\n- Bug found in login flow\n- Need to update existing story TEST-123"
        }
        
        success, create_response = self.run_test("Create Analysis", "POST", "analysis/create", 200, analysis_data)
        
        if not success:
            return False
        
        analysis_id = create_response.get('analysis_id')
        if not analysis_id:
            self.log_test("Analysis ID Retrieved", False, "No analysis_id in response")
            return False
        
        self.log_test("Analysis ID Retrieved", True, f"ID: {analysis_id}")
        
        # Test getting specific analysis
        success, analysis = self.run_test("Get Analysis by ID", "GET", f"analysis/{analysis_id}", 200)
        
        # Test getting all analyses
        success, all_analyses = self.run_test("Get All Analyses", "GET", "analysis", 200)
        
        # Test modifying a proposal (if proposals exist)
        if analysis and analysis.get('proposed_changes'):
            modify_data = {
                "index": 0,
                "summary": "Updated test summary",
                "description": "Updated test description"
            }
            success, _ = self.run_test("Modify Proposal", "PUT", f"analysis/{analysis_id}/modify", 200, modify_data)
        
        # Test approval flow
        approval_data = {
            "approved_indices": [0] if analysis and analysis.get('proposed_changes') else [],
            "rejected_indices": []
        }
        success, _ = self.run_test("Approve Proposals", "POST", f"analysis/{analysis_id}/approve", 200, approval_data)
        
        # Test rejection
        success, _ = self.run_test("Reject Analysis", "DELETE", f"analysis/{analysis_id}", 200)
        
        return True

    def test_error_handling(self):
        """Test error handling for invalid requests"""
        print("\n🚨 Testing Error Handling...")
        
        # Test invalid analysis ID
        success, _ = self.run_test("Invalid Analysis ID", "GET", "analysis/invalid-id", 404)
        
        # Test creating analysis without config
        # First, let's clear config by trying to create analysis without proper Jira setup
        analysis_data = {
            "jira_project_key": "INVALID",
            "client_name": "Test Client", 
            "project_name": "Test Project",
            "meeting_minutes": "Test minutes"
        }
        
        # This might fail due to Jira connection issues, which is expected
        self.run_test("Analysis Without Valid Jira", "POST", "analysis/create", 400)
        
        return True

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting Jira Sync API Tests...")
        print(f"Testing against: {self.base_url}")
        
        # Test basic connectivity
        self.test_root_endpoint()
        
        # Test Jira configuration
        self.test_jira_config_flow()
        
        # Test analysis flow
        self.test_analysis_flow()
        
        # Test error handling
        self.test_error_handling()
        
        # Print summary
        print(f"\n📊 Test Summary:")
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run)*100:.1f}%")
        
        return self.tests_passed, self.tests_run, self.test_results

def main():
    tester = JiraSyncAPITester()
    passed, total, results = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/backend_test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'passed': passed,
                'total': total,
                'success_rate': (passed/total)*100 if total > 0 else 0
            },
            'results': results
        }, f, indent=2)
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())