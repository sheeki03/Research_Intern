#!/usr/bin/env python3
"""
Test script to verify DocSend browser initialization fixes.
Run this to test if the browser setup works in your environment.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.docsend_client import DocSendClient

def test_browser_initialization():
    """Test browser initialization with the new fixes."""
    print("🧪 Testing DocSend browser initialization fixes...")
    print("=" * 60)
    
    try:
        # Initialize DocSend client
        print("1. Creating DocSendClient...")
        client = DocSendClient(preferred_browser='auto')
        print("   ✅ DocSendClient created successfully")
        
        # Test browser detection
        print("\n2. Detecting available browsers...")
        available_browsers = client._detect_available_browsers()
        print(f"   📋 Available browsers: {available_browsers}")
        
        # Test browser initialization
        print("\n3. Testing browser initialization...")
        browser = client._init_browser()
        print("   ✅ Browser initialized successfully!")
        
        # Test basic navigation
        print("\n4. Testing basic browser functionality...")
        browser.get("https://www.google.com")
        title = browser.title
        print(f"   📄 Page title: {title}")
        
        if "Google" in title:
            print("   ✅ Browser navigation working correctly!")
        else:
            print("   ⚠️ Unexpected page title, but browser is functional")
        
        # Clean up
        print("\n5. Cleaning up...")
        browser.quit()
        print("   ✅ Browser closed successfully")
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED! DocSend browser setup is working correctly.")
        print("   You can now use DocSend processing in your Streamlit app.")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        print("\n" + "=" * 60)
        print("🔧 TROUBLESHOOTING STEPS:")
        print("1. Ensure you're running in the correct Docker container")
        print("2. Check if Chrome is installed: google-chrome --version")
        print("3. Verify container has all dependencies from updated Dockerfile")
        print("4. Check container logs for additional error details")
        return False

if __name__ == "__main__":
    success = test_browser_initialization()
    sys.exit(0 if success else 1) 