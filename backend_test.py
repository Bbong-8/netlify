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
        self.test_drive_link = "https://drive.google.com/drive/folders/191XLWHWCx-532MN-vtZKRDbCvxCIaerZ"

    def run_test(self, name, method, endpoint, expected_status, data=None, timeout=30):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if endpoint else self.api_url
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=timeout)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=timeout)

            print(f"   Response Status: {response.status_code}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    print(f"   Response: {json.dumps(response_data, indent=2)[:300]}...")
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
            print(f"❌ Failed - Request timeout after {timeout}s")
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

    def test_folder_structure_valid_link(self):
        """Test folder structure with valid public Drive link"""
        print(f"   Testing with Drive link: {self.test_drive_link}")
        success, response = self.run_test(
            "Folder Structure - Valid Public Link",
            "POST",
            "drive/folder",
            200,
            data={"drive_link": self.test_drive_link},
            timeout=120  # Large folder may take time
        )
        
        if success:
            print(f"   Folder Name: {response.get('folder_name', 'N/A')}")
            print(f"   Total Images: {response.get('total_images', 0)}")
            print(f"   Total Folders: {response.get('total_folders', 0)}")
            print(f"   Items Count: {len(response.get('items', []))}")
            
            # Store first image ID for image test
            items = response.get('items', [])
            image_items = [item for item in items if item.get('type') == 'image']
            if image_items:
                self.first_image_id = image_items[0].get('id')
                print(f"   First Image ID: {self.first_image_id}")
            
        return success

    def test_folder_structure_invalid_link(self):
        """Test folder structure with invalid Drive link"""
        return self.run_test(
            "Folder Structure - Invalid Link",
            "POST",
            "drive/folder",
            400,
            data={"drive_link": "invalid_link"}
        )

    def test_folder_structure_missing_link(self):
        """Test folder structure without drive_link"""
        return self.run_test(
            "Folder Structure - Missing Link",
            "POST",
            "drive/folder",
            422,
            data={}
        )

    def test_image_proxy_valid_id(self):
        """Test image proxy with valid file ID"""
        if not hasattr(self, 'first_image_id') or not self.first_image_id:
            print("⚠️  Skipping test - no image ID available from folder test")
            return False
            
        success, _ = self.run_test(
            "Image Proxy - Valid File ID",
            "GET",
            f"drive/image/{self.first_image_id}",
            200,
            timeout=15
        )
        return success

    def test_image_proxy_invalid_id(self):
        """Test image proxy with invalid file ID"""
        return self.run_test(
            "Image Proxy - Invalid File ID",
            "GET",
            "drive/image/invalid_file_id",
            404
        )

    def test_cache_functionality(self):
        """Test caching by making the same request twice"""
        print("   Testing cache functionality with second request...")
        
        # First request (should be cached from previous test)
        start_time = datetime.now()
        success1, response1 = self.run_test(
            "Cache Test - Second Request",
            "POST",
            "drive/folder",
            200,
            data={"drive_link": self.test_drive_link},
            timeout=30
        )
        end_time = datetime.now()
        
        if success1:
            duration = (end_time - start_time).total_seconds()
            print(f"   Request Duration: {duration:.2f}s")
            if duration < 5:
                print("   ✅ Cache appears to be working (fast response)")
            else:
                print("   ⚠️  Cache may not be working (slow response)")
                
        return success1

    def test_clear_cache(self):
        """Test cache clearing functionality"""
        # Extract folder ID from test link
        import re
        folder_id_match = re.search(r'folders/([a-zA-Z0-9-_]+)', self.test_drive_link)
        if not folder_id_match:
            print("⚠️  Skipping test - cannot extract folder ID")
            return False
            
        folder_id = folder_id_match.group(1)
        return self.run_test(
            "Clear Cache",
            "DELETE",
            f"drive/cache/{folder_id}",
            200
        )

def main():
    print("🚀 Starting Google Drive Slideshow API Tests (Web Scraping Version)")
    print("=" * 70)
    
    # Setup
    tester = DriveAPITester()
    
    # Run tests
    print("\n📋 Running API Endpoint Tests...")
    
    # Test basic endpoints
    tester.test_root_endpoint()
    
    # Test folder structure endpoints
    tester.test_folder_structure_valid_link()
    tester.test_folder_structure_invalid_link()
    tester.test_folder_structure_missing_link()
    
    # Test image proxy endpoints
    tester.test_image_proxy_valid_id()
    tester.test_image_proxy_invalid_id()
    
    # Test caching functionality
    tester.test_cache_functionality()
    tester.test_clear_cache()

    # Print results
    print("\n" + "=" * 70)
    print(f"📊 Test Results: {tester.tests_passed}/{tester.tests_run} tests passed")
    
    if tester.tests_passed == tester.tests_run:
        print("🎉 All tests passed!")
        return 0
    else:
        print(f"⚠️  {tester.tests_run - tester.tests_passed} tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())