from rest_framework.test import APIClient
from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework.test import APITestCase

path = 'http://127.0.0.1:8000'

class ProteinTest(APITestCase):
    def test_response(self):
        client = APIClient()
        response = client.get(path + '/api/protein/500/')
        assert response.status_code == 200

    def test_omaid(self):
        client = APIClient()
        response = client.get(path + '/api/protein/300/')
        self.assertEqual(response.data['omaid'], 'YEAST00300')

    def test_domain_url(self):
        client = APIClient()
        response = client.get(path + '/api/protein/909/')
        self.assertEqual(response.data['domains'], 'http://testserver/api/protein/909/domains/')


