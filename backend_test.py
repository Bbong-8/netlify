import requests
import sys
import json
from datetime import datetime

class DriveAPITester:
    def __init__(self, base_url="https://drive-slideshow.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.session_id = None

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else self.api_url
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, params=params, timeout=10)

            print(f"   Response Status: {response.status_code}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:200]}...")
                    return True, response_data
                except:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text[:200]}")
                return False, {}

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout")
            return False, {}
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_root_endpoint(self):
        """Test the root API endpoint"""
        return self.run_test(
            "Root API Endpoint",
            "GET",
            "",
            200
        )

    def test_drive_connect(self):
        """Test Google Drive OAuth initiation"""
        success, response = self.run_test(
            "Drive OAuth Connect",
            "GET",
            "drive/connect",
            200
        )
        
        if success and 'authorization_url' in response and 'session_id' in response:
            self.session_id = response['session_id']
            print(f"   Session ID: {self.session_id}")
            print(f"   Auth URL: {response['authorization_url'][:100]}...")
            return True
        return False

    def test_folder_no_session(self):
        """Test folder endpoint without session"""
        return self.run_test(
            "Folder - No Session",
            "POST",
            "drive/folder",
            422,  # Missing required query parameter
            data={"drive_link": "https://drive.google.com/drive/folders/test"}
        )

    def test_folder_invalid_session(self):
        """Test folder endpoint with invalid session"""
        return self.run_test(
            "Folder - Invalid Session",
            "POST",
            "drive/folder",
            401,  # Not authenticated
            data={"drive_link": "https://drive.google.com/drive/folders/test"},
            params={"session_id": "invalid_session_id"}
        )

    def test_folder_invalid_link(self):
        """Test folder endpoint with invalid link format"""
        if not self.session_id:
            print("⚠️  Skipping test - no session ID available")
            return False
            
        return self.run_test(
            "Folder - Invalid Link Format",
            "POST",
            "drive/folder",
            400,  # Bad request due to invalid link format
            data={"drive_link": "invalid_link"},
            params={"session_id": self.session_id}
        )

    def test_drive_status_invalid_session(self):
        """Test drive status with invalid session"""
        return self.run_test(
            "Drive Status - Invalid Session",
            "GET",
            "drive/status",
            200,
            params={"session_id": "invalid_session_id"}
        )

    def test_drive_image_no_session(self):
        """Test drive image endpoint without session"""
        return self.run_test(
            "Drive Image - No Session",
            "GET",
            "drive/image/test_file_id",
            422  # Missing required query parameter
        )

    def test_drive_image_invalid_session(self):
        """Test drive image endpoint with invalid session"""
        return self.run_test(
            "Drive Image - Invalid Session",
            "GET",
            "drive/image/test_file_id",
            401,  # Not authenticated
            params={"session_id": "invalid_session_id"}
        )

    def test_drive_callback_missing_params(self):
        """Test OAuth callback without required parameters"""
        return self.run_test(
            "Drive Callback - Missing Params",
            "GET",
            "drive/callback",
            422  # Missing required query parameters
        )

def main():
    print("🚀 Starting Google Drive Slideshow API Tests")
    print("=" * 60)
    
    # Setup
    tester = DriveAPITester()
    
    # Run tests
    print("\n📋 Running API Endpoint Tests...")
    
    # Test basic endpoints
    tester.test_root_endpoint()
    tester.test_drive_connect()
    
    # Test folder endpoints (OAuth-only)
    tester.test_folder_no_session()
    tester.test_folder_invalid_session()
    tester.test_folder_invalid_link()
    
    # Test status and image endpoints
    tester.test_drive_status_invalid_session()
    tester.test_drive_image_no_session()
    tester.test_drive_image_invalid_session()
    
    # Test callback endpoint
    tester.test_drive_callback_missing_params()

    # Print results
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {tester.tests_run - tester.tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())