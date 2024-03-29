import json
from rest_framework.test import APIClient, APITestCase
import re


def get_next_url(link):
    m = re.search(r'<(?P<url>[^>]+)>;[^,]*rel="next"', link)
    if m is not None:
        return m.group('url')
    return None


class ProteinTest(APITestCase):
    def test_response(self):
        client = APIClient()
        response = client.get('/api/protein/500/')
        self.assertEqual(200, response.status_code)

    def test_omaid(self):
        client = APIClient()
        response = client.get('/api/protein/300/')
        self.assertEqual(response.data['omaid'], 'YEAST00300')

    def test_unknown_protein_id(self):
        response = APIClient().get('/api/protein/cs3sfg21aa2/')
        self.assertEqual(404, response.status_code)
        res = json.loads(response.content.decode())
        self.assertIn('unknown', res['detail'])

    def test_unambigous_protein_id(self):
        response = APIClient().get('/api/protein/MAL/')
        self.assertEqual(404, response.status_code)
        res = json.loads(response.content.decode())
        self.assertIn('not unique', res['detail'])

    def test_protein_without_hog_membership(self):
        response = APIClient().get('/api/protein/2/')
        self.assertEqual(200, response.status_code)
        self.assertEqual('', response.data['oma_hog_id'])
        self.assertIsNone(response.data['oma_hog_members'])

    def test_protein_without_oma_group(self):
        response = APIClient().get('/api/protein/1/')
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, response.data['oma_group'])
        self.assertIsNone(response.data['oma_group_url'])

    def test_protein_links(self):
        client = APIClient()
        response = client.get('/api/protein/909/')
        self.assertEqual(response.data['domains'], 'http://testserver/api/protein/909/domains/')
        self.assertEqual(response.data['orthologs'], 'http://testserver/api/protein/909/orthologs/')
        self.assertEqual(response.data['gene_ontology'], 'http://testserver/api/protein/909/gene_ontology/')
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

    def test_bulk_retrieval_of_proteins(self):
        client = APIClient()
        response = client.post('/api/protein/bulk_retrieve/',
                               {'ids': [1, 'YEAST12', 'NON_EXISTING_ID', 66]},
                               format='json')
        self.assertEqual(200, response.status_code)
        self.assertEqual(4, len(response.data))
        dat = response.data
        self.assertEqual(dat[0]['query_id'], str(1))
        self.assertEqual(dat[0]['target']['entry_nr'], 1)
        self.assertIsNone(dat[2]['target'])

    def test_legacyversion_bulk_retrieve(self):
        client = APIClient(HTTP_ACCEPT="application/json; version=1.6")
        response = client.post('/api/protein/bulk_retrieve/',
                               {'ids': [1, 'YEAST12', 'NON_EXISTING_ID', 66]},
                               format="json")
        self.assertEqual(200, response.status_code)
        self.assertEqual(3, len(response.data))
        self.assertEqual([1, 12, 66], [x['entry_nr'] for x in response.data])


class HOGsTest(APITestCase):
    def test_rootlevel_of_subhog(self):
        response = APIClient().get('/api/hog/HOG:0000515.1a/')
        self.assertEqual(1, len(response.data))
        self.assertEqual(response.data[0]['level'], 'Saccharomyces cerevisiae (strain ATCC 204508 / S288c)')

    def test_rootlevel_with_roothog_root(self):
        response = APIClient().get('/api/hog/HOG:0000515.1a/', {'level': 'root'})
        self.assertEqual(1, len(response.data))
        self.assertEqual('Saccharomycetaceae', response.data[0]['level'])

    def test_level_attribute_not_present_in_children_hogs(self):
        hog_id = "HOG:0000002"
        response = APIClient().get('/api/hog/{}/'.format(hog_id))
        self.assertEqual(200, response.status_code)
        result = json.loads(response.content.decode())
        self.assertEqual(1, len(result))
        result = result[0]
        self.assertEqual('Eukaryota', result['level'], 'unexpected root level')
        self.assertLess(1, len(result['children_hogs']))
        for child in result['children_hogs']:
            self.assertIn(hog_id, child['hog_id'])
            self.assertNotEqual(hog_id, child['hog_id'])
            with self.assertRaises(KeyError):
                child['level']

    def test_hogdetail_with_level_returns_multiple_subhogs(self):
        hog_id, level = "HOG:0000192", "Saccharomycetaceae"
        client = APIClient()
        response = client.get('/api/hog/{}/'.format(hog_id), {'level': level})
        result = json.loads(response.content.decode())
        self.assertEqual(5, len(result))
        for res in result:
            self.assertIn(hog_id, res['hog_id'])
            self.assertNotEqual(hog_id, res['hog_id'])
            self.assertEqual(level, res['level'])
        parents = result[0]['parent_hogs']
        self.assertEqual(1, len(parents))
        # let's check that the parent link works and returns just a single hog
        response = client.get(parents[0]['levels_url'])
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(response.data))
        self.assertEqual(hog_id, response.data[0]['hog_id'])

    def test_hog_members(self):
        client = APIClient()
        response = client.get('/api/hog/HOG:0000365/members/', format='json')
        protein_url = response.data['members'][0]['entry_url']
        response_2 = client.get(protein_url, format='json')
        self.assertIn('HOG:0000365', response_2.data['oma_hog_id'])

    def test_nr_hogs_at_level(self):
        client = APIClient()
        for lev in ('Eukaryota', 'Alveolata'):
            response = client.get('/api/hog/', {'level': lev, 'per_page': 500})
            cnts = len(response.data)
            while get_next_url(response['Link']) is not None:
                response = client.get(get_next_url(response['Link']))
                cnts += len(response.data)
            self.assertEqual(int(response['X-Total-Count']), cnts)

    def test_members_at_low_level(self):
        """check that result does not contain any member outside the requested clade"""
        response = APIClient().get('/api/hog/HOG:0000002/members/?level=Fungi')
        self.assertEqual(200, response.status_code)
        involved_species = [m['omaid'][0:5] for m in response.data['members']]
        self.assertNotIn('PLAF7', involved_species)

    def test_members_by_protein_id(self):
        response = APIClient().get('/api/hog/YEAST12/members/')
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(response.data['members']))

    def test_members_by_protein_id_and_level(self):
        response = APIClient().get('/api/hog/YEAST12/members/', {'level': 'Eukaryota'})
        self.assertEqual(200, response.status_code)
        self.assertEqual(5, len(response.data['members']))


class AncestralSyntenyTest(APITestCase):
    def test_Fungi_ancestral_example(self):
        response = APIClient().get('/api/synteny/', {'level': "Fungi"})
        self.assertEqual(200, response.status_code)
        self.assertLessEqual(200, len(response.data))

    def test_Fungi_ancestral_invalid_center_hog_example(self):
        response = APIClient().get('/api/synteny/HOG:02s.1a', {'level': "Fungi"})
        self.assertEqual(404, response.status_code)



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
        self.assertEqual(4, int(response["X-Total-Count"]))
        self.assertEqual(4, len(response.data))

    def test_genome_info(self):
        response = APIClient().get('/api/genome/YEAST/')
        self.assertEqual(200, response.status_code)
        self.assertEqual('YEAST', response.data['code'])

    def test_member_proteins(self):
        client = APIClient()
        # test a paginated view
        response = client.get('/api/genome/YEAST/proteins/')
        self.assertEqual(6352, int(response['x-total-count']))
        self.assertIn('next', response['link'])
        self.assertIn('last', response['link'])
        self.assertLessEqual(100, len(response.data))

        client = APIClient()
        response = client.get('/api/genome/ASHGO/proteins/', {'per_page': 5000})
        self.assertEqual(4757, int(response['x-total-count']))
        with self.assertRaises(KeyError):
            response['link']
        self.assertEqual(4757, len(response.data))


class TaxonomyTest(APITestCase):
    def test_root(self):
        client = APIClient()
        response = client.get('/api/taxonomy/Opisthokonta/?type=newick&collapse=no')
        self.assertEqual('Opisthokonta', response.data['root_taxon']['name'])

    def test_root_collapsed_always_severl_children(self):
        client = APIClient()
        response = client.get('/api/taxonomy/Opisthokonta/?type=json')
        self.assertEqual(200, response.status_code)
        res = json.loads(response.content.decode())

        def rec_trav(n):
            if "children" in n:
                self.assertGreaterEqual(len(n['children']), 2)
                for c in n['children']:
                    rec_trav(c)
        rec_trav(res)

    def test_members(self):
        client = APIClient()
        url = '/api/taxonomy/?members=284811,559292,4893,4892,4891,147537,284812,716545,451866,4890,451864&type=newick'
        response = client.get(url, format='json')
        self.assertNotIn('Alveolata', response.data['newick'])

    def test_member_contains_lca(self):
        client = APIClient()
        response = client.get('/api/taxonomy/?members=559292&members=284811')
        self.assertEqual(200, response.status_code)

    def test_cross_check_taxon_ids(self):
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
        involved_species = set([p['entry_1']['omaid'][0:5] for p in response.data])
        self.assertEqual(set(['YEAST']), involved_species)

    def test_pairs_with_and_without_reltype_limits(self):
        client = APIClient()
        response = client.get('/api/pairs/YEAST/PLAF7/')
        self.assertEqual(200, response.status_code)
        response_filt = client.get('/api/pairs/YEAST/PLAF7/?rel_type=1:1')
        self.assertEqual(200, response_filt.status_code)
        self.assertLess(len(response_filt.data), len(response.data))

    def test_empty_result_if_inexisting_rel_type(self):
        response = APIClient().get('/api/pairs/YEAST/PLAF7/?rel_type=2:6')
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.data)


class XRefLookupTest(APITestCase):
    def test_no_query_param(self):
        response = APIClient().get('/api/xref/')
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.data)

    def test_prefix_too_short(self):
        response = APIClient().get('/api/xref/?search=MA')
        self.assertEqual(200, response.status_code)
        self.assertEqual([], response.data)

    def test_existing_pattern_in_search_xref(self):
        response = APIClient().get('/api/xref/?search=MaL')
        self.assertEqual(200, response.status_code)
        self.assertLess(0, len(response.data))
        for hit in response.data:
            self.assertIn('mal', hit['xref'].lower())


class SequenceIdentifyTest(APITestCase):
    existing_query = 'ALTDVAAIVKDNPD'
    inexisting_query = 'ALTDVAAVAVKDNPD'
    query_with_mutliple_matches = "ADRIA"
    multi_match_pattern = "PLRDFVKSHGGHTVISKILIANNGIAAVKEIRSVR"

    def test_too_short_query(self):
        response = APIClient().get('/api/sequence/?query=AA')
        self.assertEqual(400, response.status_code)

    def test_exact_match(self):
        response = APIClient().get('/api/sequence/?query='+self.existing_query)
        self.assertEqual(200, response.status_code)
        self.assertEqual('exact match', response.data['identified_by'])

    def test_no_hit_if_exact_but_sequence_differ(self):
        response = APIClient().get('/api/sequence/?search=exact&query='+self.inexisting_query)
        self.assertEqual(0, len(response.data['targets']))

    def test_no_hit_if_exact_but_not_full_length(self):
        response = APIClient().get('/api/sequence/?search=exact&full_length=True&query='+self.existing_query)
        self.assertEqual(0, len(response.data['targets']))

    def test_several_exact_hits(self):
        response = APIClient().get('/api/sequence/?search=exact&query=' + self.query_with_mutliple_matches)
        self.assertLess(1, len(response.data['targets']))
        self.assertEqual('exact match', response.data['identified_by'])

    def test_several_approx_hits(self):
        response = APIClient().get('/api/sequence/?search=approximate&query='+self.multi_match_pattern)
        self.assertLess(1, len(response.data['targets']))
        self.assertEqual('approximate match', response.data['identified_by'])

    def test_invalid_search_param(self):
        response = APIClient().get('/api/sequence/?search=blabla&query='+self.existing_query)
        self.assertEqual(400, response.status_code)


class FunctionPropagationTest(APITestCase):
    def test_map_existing_sequence_and_expect_same_annotations(self):
        client = APIClient()
        query = 'YEAST00012'
        protein = json.loads(client.get('/api/protein/'+query+'/').content.decode())
        gos_pred = client.get('/api/function/?query='+protein['sequence'])
        self.assertEqual('Exact:'+query, gos_pred.data[0]['With'])
        onto = client.get('/api/protein/'+query+'/ontology/')
        gos_pred = sorted([(z['GO_ID'], z['GO_name']) for z in gos_pred.data])
        onto = sorted(set([(z['GO_term'], z['name']) for z in onto.data]))
        self.assertEqual(onto, gos_pred)

    def test_with_non_aa_get_400_exit(self):
        response = APIClient().get('/api/function/?query=BSBBbAop  qs')
        self.assertEqual(400, response.status_code)

    def test_trim_invalid_aa_and_find_approx_match(self):
        response = APIClient().get('/api/function/?query=KGPYGGLRF HPSVNLSILK FLGFEIFKN')
        self.assertEqual(200, response.status_code)
        annos = json.loads(response.content.decode())
        self.assertLess(0, len(annos))
        self.assertTrue(annos[0]['With'].startswith('Approx:YEAST00012'))

