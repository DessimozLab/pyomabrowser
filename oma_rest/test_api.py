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

    def test_domains(self):
        client = APIClient()
        response = client.get(path + '/api/protein/77/domains/')
        self.assertEqual(response.data['seq_id'], '3581baa88a30fe9640d9315247c5e081')

    def test_ontology_url(self):
        client = APIClient()
        response = client.get(path + '/api/protein/105/')
        self.assertEqual(response.data['ontology'], 'http://testserver/api/protein/105/ontology/')

    def test_ontologies(self):
        client = APIClient()
        response = client.get(path + '/api/protein/78/ontology/',format = 'json')
        self.assertEqual('GO:0005770',response.data[0]['GO_term'])

    #check that orthologues belong to the same hog
    def test_orthologues(self):
        client = APIClient()
        response = client.get(path + '/api/protein/23/orthologs/',format = 'json')
        protein_url = response.data[0]['ortholog']['entry_url']
        response_2 = client.get(protein_url, format = 'json')
        self.assertEqual('HOG:0000008',response_2.data['oma_hog_id'])

    def test_xref(self):
        client = APIClient()
        response = client.get(path + '/api/protein/50/xref/',format = 'json')
        self.assertEqual(int(50),response.data[0]['entry_nr'])

class HOGsTest(APITestCase):
    def test_rootlevel(self):
        client = APIClient()
        response = client.get(path + '/api/hogs/HOG:0000515.1a/')
        self.assertEqual(response.data['root_level'], 'Saccharomyces cerevisiae (strain ATCC 204508 / S288c)')

    def test_hog_members(self):
        client = APIClient()
        response = client.get(path + '/api/hogs/HOG:0000365/members/', format='json')
        protein_url = response.data['members'][0]['entry_url']
        response_2 = client.get(protein_url, format='json')
        self.assertIn('HOG:0000365', response_2.data['oma_hog_id'])

class GroupTest(APITestCase):
    #test group member is in the correct group
    def test_group_members(self):
        client = APIClient()
        response = client.get(path + '/api/group/500/', format='json')
        protein_url = response.data['members'][0]['entry_url']
        response_2 = client.get(protein_url, format='json')
        self.assertEqual(int(500), response_2.data['oma_group'])

class GenomeTest(APITestCase):
    def test_member_proteins(self):
        client = APIClient()
        response = client.get(path + '/api/genome/YEAST/proteins_list/')
        self.assertEqual(int(6352), response.data['count'])

        client = APIClient()
        response = client.get(path + '/api/genome/ASHGO/proteins_list/')
        self.assertEqual(int(4757), response.data['count'])







