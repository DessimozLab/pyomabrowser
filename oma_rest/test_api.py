import json

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

    def test_invalid_group_raises_error(self):
        client = APIClient()
        response = client.get('/api/group/ADRIANADRIAN/')
        self.assertEqual(404, response.status_code)

    def test_group_by_groupnr(self):
        client = APIClient()
        response = client.get('/api/group/30/')
        self.assertEqual(200, response.status_code)
        data = json.loads(response.content.decode())
        self.assertEqual(30, data['group_nr'])

    def test_group_by_entry_id(self):
        client = APIClient()
        response = client.get('/api/group/YEAST00055/')
        self.assertEqual(200, response.status_code)
        members = [z['omaid'] for z in response.data['members']]
        self.assertIn('YEAST00055', members)

    def test_group_by_inexisting_entry_id(self):
        response = APIClient().get('/api/group/YEAST09999/')
        self.assertEqual(404, response.status_code)

    def test_group_edge_cases(self):
        response = APIClient().get('/api/group/0/')
        self.assertEqual(404, response.status_code)

    def test_protein_without_group(self):
        response = APIClient().get('/api/group/YEAST00001/')
        self.assertEqual(200, response.status_code)
        self.assertEqual({}, response.data)

    def test_close_group_exists(self):
        client = APIClient()
        response = client.get('/api/group/YEAST00012/close_groups/')
        self.assertEqual(200, response.status_code)
        self.assertIsInstance(response.data, list)


class GenomeTest(APITestCase):
    def test_genome_list(self):
        response = APIClient().get('/api/genome/')
        self.assertEqual(200, response.status_code)
        self.assertEqual(4, response.data['count'])

    def test_genome_info(self):
        response = APIClient().get('/api/genome/YEAST/')
        self.assertEqual(200, response.status_code)
        self.assertEqual('YEAST', response.data['code'])

    def test_member_proteins(self):
        client = APIClient()
        response = client.get('/api/genome/YEAST/proteins/')
        self.assertEqual(int(6352), response.data['count'])

        client = APIClient()
        response = client.get('/api/genome/ASHGO/proteins/')
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


class PairwiseRelationsTest(APITestCase):
    def test_same_species(self):
        response = APIClient().get('/api/pairs/YEAST/YEAST/')
        self.assertEqual(200, response.status_code)
        self.assertLess(1000, response.data['count'])
        involved_species = set([p['entry_1']['omaid'][0:5] for p in response.data['results']])
        self.assertEqual(set(['YEAST']), involved_species)

    def test_pairs_with_and_without_reltype_limits(self):
        client = APIClient()
        response = client.get('/api/pairs/YEAST/PLAF7/')
        self.assertEqual(200, response.status_code)
        c_unfiltered = response.data['count']
        response_filt = client.get('/api/pairs/YEAST/PLAF7/?rel_type=1:1')
        self.assertEqual(200, response_filt.status_code)
        c_filtered = response_filt.data['count']
        self.assertLess(c_filtered, c_unfiltered)

    def test_empty_result_if_inexisting_rel_type(self):
        response = APIClient().get('/api/pairs/YEAST/PLAF7/?rel_type=2:6')
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.data['count'])
        self.assertEqual([], response.data['results'])


class XRefLookupTest(APITestCase):
    def test_no_query_param(self):
        response = APIClient().get('/api/xref/')
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.data)

    def test_prefix_too_short(self):
        response = APIClient().get('/api/xref/?search=MA')
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.data)

    def test_existing_prefix(self):
        response = APIClient().get('/api/xref/?search=MAL')
        self.assertEqual(200, response.status_code)
        self.assertLess(0, len(response.data))
        for hit in response.data:
            self.assertTrue(hit['xref'].lower().startswith('mal'))