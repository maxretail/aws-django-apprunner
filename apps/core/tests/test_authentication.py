from django.test import TestCase, Client, override_settings
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
import base64
import json
import os

User = get_user_model()

# Use fixed API keys for testing
TEST_API_KEY_1 = 'test-api-key-123'
TEST_API_KEY_2 = 'test-api-key-456'
TEST_API_KEYS = [TEST_API_KEY_1, TEST_API_KEY_2]

@override_settings(API_KEYS=TEST_API_KEYS)
class ApiKeyAuthenticationTest(TestCase):
    """Test the API Key authentication methods"""
    
    def setUp(self):
        """Set up test data"""
        # Create a test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpassword'
        )
        
        # Create a test endpoint URL (using the protected path that requires auth)
        self.url = '/protected/'
        
        # Create a test client
        self.client = Client()
    
    def test_unauthenticated_request(self):
        """Test that unauthenticated requests are rejected"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_x_api_key_header(self):
        """Test authentication using X-API-KEY header with first key"""
        response = self.client.get(
            self.url,
            HTTP_X_API_KEY=TEST_API_KEY_1
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test with second key
        response = self.client.get(
            self.url,
            HTTP_X_API_KEY=TEST_API_KEY_2
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test invalid API key
        response = self.client.get(
            self.url,
            HTTP_X_API_KEY='invalid-key'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_authorization_header_apikey(self):
        """Test authentication using Authorization header with ApiKey format"""
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f'ApiKey {TEST_API_KEY_1}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test with second key
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f'ApiKey {TEST_API_KEY_2}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test invalid API key
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION='ApiKey invalid-key'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_basic_auth(self):
        """Test authentication using HTTP Basic Auth with password as API key"""
        credentials = base64.b64encode(b'username:' + TEST_API_KEY_1.encode()).decode()
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f'Basic {credentials}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test with second key
        credentials = base64.b64encode(b'username:' + TEST_API_KEY_2.encode()).decode()
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f'Basic {credentials}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test invalid API key
        credentials = base64.b64encode(b'username:invalid-key').decode()
        response = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=f'Basic {credentials}'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_query_parameter(self):
        """Test authentication using API key as query parameter"""
        response = self.client.get(
            f'{self.url}?api_key={TEST_API_KEY_1}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test with second key
        response = self.client.get(
            f'{self.url}?api_key={TEST_API_KEY_2}'
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test invalid API key
        response = self.client.get(
            f'{self.url}?api_key=invalid-key'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_n8n_style_request(self):
        """Test authentication specifically formatted like an n8n request"""
        # Create credentials in the format n8n uses
        credentials = base64.b64encode(b'n8n:' + TEST_API_KEY_1.encode()).decode()
        
        # Add headers that n8n might include
        headers = {
            'HTTP_AUTHORIZATION': f'Basic {credentials}',
            'HTTP_ACCEPT': 'application/json',
            'HTTP_USER_AGENT': 'n8n',
        }
        
        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Test with second key
        credentials = base64.b64encode(b'n8n:' + TEST_API_KEY_2.encode()).decode()
        headers['HTTP_AUTHORIZATION'] = f'Basic {credentials}'
        
        response = self.client.get(self.url, **headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verify response contains valid JSON
        try:
            content = json.loads(response.content)
            self.assertIn('message', content)
        except json.JSONDecodeError:
            self.fail("Response is not valid JSON")

class NoApiKeysTest(TestCase):
    """Test behavior when no API keys are configured"""
    
    def setUp(self):
        """Set up test data"""
        self.url = '/protected/'
        self.client = Client()
    
    @override_settings(API_KEYS=[])
    def test_no_api_keys_configured(self):
        """Test that requests are properly rejected when no API keys are configured"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        content = json.loads(response.content)
        self.assertEqual(content['error'], 'No API keys configured on the server') 