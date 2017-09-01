from rest_framework.test import APIClient, APITestCase


class ProteinTest(APITestCase):
    def test_response(self):
        client = APIClient()
        response = client.get('/api/protein/500/')
        self.assertEqual(200, response.status_code)

    def test_omaid(self):
        client = APIClient()
        response = client.get('/api/protein/300/')
        self.assertEqual(response.data['omaid'], 'YEAST00300')

    def test_protein_links(self):
        client = APIClient()
        response = client.get('/api/protein/909/')
        self.assertEqual(response.data['domains'], 'http://testserver/api/protein/909/domains/')
        self.assertEqual(response.data['orthologs'], 'http://testserver/api/protein/909/orthologs/')
        self.assertEqual(response.data['ontology'], 'http://testserver/api/protein/909/ontology/')
        self.assertEqual(response.data['xref'], 'http://testserver/api/protein/909/xref/')

    def test_domains(self):
        client = APIClient()
        response = client.get('/api/protein/77/domains/')
        self.assertEqual(response.data['seq_id'], '3581baa88a30fe9640d9315247c5e081')

    def test_ontologies(self):
        client = APIClient()
        response = client.get('/api/protein/78/ontology/', format='json')
        all_terms = [z['GO_term'] for z in response.data]
        self.assertIn('GO:0005770', all_terms)

    # check that orthologues belong to the same hog
    def test_orthologues(self):
        client = APIClient()
        response = client.get('/api/protein/23/orthologs/', format='json')
        protein_url = response.data[0]['entry_url']
        response_2 = client.get(protein_url, format='json')
        self.assertEqual('HOG:0000008', response_2.data['oma_hog_id'])

    def test_xref(self):
        client = APIClient()
        response = client.get('/api/protein/50/xref/', format='json')
        self.assertEqual(int(50), response.data[0]['entry_nr'])


class HOGsTest(APITestCase):
    def test_rootlevel(self):
        client = APIClient()
        response = client.get('/api/hog/HOG:0000515.1a/')
        self.assertEqual(response.data['root_level'], 'Saccharomyces cerevisiae (strain ATCC 204508 / S288c)')

    def test_hog_members(self):
        client = APIClient()
        response = client.get('/api/hog/HOG:0000365/members/', format='json')
        protein_url = response.data['members'][0]['entry_url']
        response_2 = client.get(protein_url, format='json')
        self.assertIn('HOG:0000365', response_2.data['oma_hog_id'])


class GroupTest(APITestCase):
    # test group member is in the correct group
    def test_group_members(self):
        client = APIClient()
        response = client.get('/api/group/500/', format='json')
        protein_url = response.data['members'][0]['entry_url']
        response_2 = client.get(protein_url, format='json')
        self.assertEqual(500, response_2.data['oma_group'])


class GenomeTest(APITestCase):
    def test_member_proteins(self):
        client = APIClient()
        response = client.get('/api/genome/YEAST/proteins_list/')
        self.assertEqual(int(6352), response.data['count'])

        client = APIClient()
        response = client.get('/api/genome/ASHGO/proteins_list/')
        self.assertEqual(int(4757), response.data['count'])


class TaxonomyTest(APITestCase):
    def test_root(self):
        client = APIClient()
        response = client.get('/api/taxonomy/Opisthokonta/?type=newick', format='json')
        self.assertEqual('Opisthokonta', response.data['root_taxon']['name'])

    def test_members(self):
        client = APIClient()
        url = '/api/taxonomy/?members=284811,559292,4893,4892,4891,147537,284812,716545,451866,4890,451864&type=newick'
        response = client.get(url, format='json')
        self.assertNotIn('Alveolata', response.data['newick'])

    def cross_check_taxon_ids(self):
        client = APIClient()
        url1 = '/api/taxonomy/?type=newick'
        response1 = client.get(url1, format='json')
        url2 = '/api/taxonomy/Eukaryota/?type=newick'
        response2 = client.get(url2, format='json')
        self.assertEqual(response1.data['root_taxon']['taxon_id'], response2.data['root_taxon']['taxon_id'])
