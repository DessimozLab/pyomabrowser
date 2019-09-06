from __future__ import print_function, absolute_import, division
import json
from django.test import TestCase
from django.urls import reverse
import re
import collections


def decode_replycontent(reply):
    content_type = reply['Content-Type']
    match = re.search('charset=(?P<encoding>[A-Za-z0-9-]+)', content_type)
    enc = 'ascii' if match is None else match.group('encoding')
    return reply.content.decode(enc)


class EntryFasta_Test(TestCase):
    def test_extract_fasta_formatted_entry(self):
        query = 'YEAST{:05d}'.format(12)
        reply = self.client.get(reverse('entry_fasta', args=[query]))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply['Content-Type'], 'text/plain')
        self.assertIn('>{}'.format(query), decode_replycontent(reply))


class VPairsViews_Test(TestCase):
    def test_html_contains_orthologs(self):
        query = 'YEAST00012'
        reply = self.client.get(reverse('pairs', args=[query]))
        self.assertEqual(reply.status_code, 200)
        content = decode_replycontent(reply)
        vps = [z.omaid for z in reply.context['vps']]
        self.assertGreater(len(vps), 0)
        api_url = re.search(r'data-url="(?P<url>[^"]*)"', content)
        self.assertIsNotNone(api_url)
        api_data = self.client.get(api_url.group('url'))
        self.assertEqual(api_data.status_code, 200)
        api_data = decode_replycontent(api_data)
        for vp in vps:
            self.assertIn(vp, api_data, 'VP {} not found on page.'.format(vp))

    def test_inexistant_query_genome(self):
        query = 'ECOLI00411'
        reply = self.client.get(reverse('pairs', args=[query]))
        self.assertEqual(reply.status_code, 404)


class HogFastaView_Test(TestCase):
    def get_fasta_and_verify_sequences_and_nr_members(self, query, level, seqs, nr_expected_members):
        if isinstance(seqs, str):
            seqs = [seqs]
        reply = self.client.get(reverse('hogs_fasta', args=[query, level]))
        self.assertEqual(reply.status_code, 200)
        content = reply.content.decode()
        self.assertEqual(content.count('>'), nr_expected_members)
        for seq in seqs:
            self.assertIn(seq, content, 'sequence {!r} not in reply')

    def test_query_sequence_in_result_at_fungi(self):
        self.get_fasta_and_verify_sequences_and_nr_members('YEAST00012', 'Fungi',
                                                           ['MTSEPEFQQAYDEIVSSVEDSKIF', 'KRVLPIISIPERVLEFRVTWEDD'], 3)

    def test_query_sequence_in_result_at_eukaryota(self):
        self.get_fasta_and_verify_sequences_and_nr_members('YEAST00012', 'Eukaryota',
                                                           ['MILYSCVVCFIVFVFHVKAYSKNKVLKYAK',
                                                            'KRVLPIISIPERVLEFRVTWEDD'], 5)


class HogView_Test(TestCase):
    def test_orthoxml(self):
        """Test retrieval of an individual orthoxml"""
        query = 'YEAST00012'
        reply = self.client.get(reverse('hogs_orthoxml', args=[query]))
        self.assertEqual(reply.status_code, 200)
        content = decode_replycontent(reply)
        self.assertIn(query, content)
        self.assertIn('orthoXML', content)

    def test_hog_success_page(self):
        query = 'YEAST00012'
        reply = self.client.get(reverse('hogs', args=[query, 'Eukaryota']))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(len(reply.context['hog_members']), 5)
        self.assertIn(query, decode_replycontent(reply))

    def test_basehog_without_orthologs(self):
        """test that page returns doesn't belong to any hog message"""
        reply = self.client.get(reverse('hogs', args=['YEAST10']))
        self.assertEqual(reply.status_code, 200)
        self.assertIn("not part of any hierarchical orthologous group", decode_replycontent(reply))

    def test_invalid_level(self):
        """test that an invalid level (level not belonging to species) will return an error message"""
        reply = self.client.get(reverse('hogs', args=['YEAST12', 'Mammalia']))
        self.assertEqual(reply.status_code, 404)


class HogVisViewTest(TestCase):
    def test_return_right_orthoxml_link(self):
        query = 'YEAST00012'
        reply = self.client.get(reverse('hog_vis', args=[query]))
        self.assertEqual(reply.status_code, 200)
        self.assertTemplateUsed(reply, "hog_iHam.html")
        expected_orthoxml_url = reverse('hogs_orthoxml', args=[query])
        expected_species_url = '/All/speciestree.nwk'
        self.assertIn('url: "{}"'.format(expected_orthoxml_url).encode('utf-8'), reply.content)
        self.assertIn('url: "{}"'.format(expected_species_url).encode('utf-8'), reply.content)

        # test that orthoxml has query gene
        orthoxml = self.client.get(expected_orthoxml_url)
        self.assertEqual(orthoxml.status_code, 200)
        self.assertIn('protId="{}"'.format(query).encode('utf-8'), orthoxml.content)

    def test_access_singleton_protein(self):
        query = 'YEAST11'  # this protein is not part of any HOG
        reply = self.client.get(reverse('hog_vis', args=[query]))
        self.assertEqual(200, reply.status_code)
        self.assertIn('is not part of any hierarchical', decode_replycontent(reply))


class SyntenyViewTester(TestCase):
    def verify_colors(self, query, window):
        reply = self.client.get(reverse('synteny', args=[query, window]))
        self.assertEqual(reply.status_code, 200)
        query_genome_genes = reply.context['md']['genes']
        ortholog_2_queryneighbors = collections.defaultdict(list)
        for neigbor in query_genome_genes.values():
            try:
                for ortho in neigbor['orthologs']:
                    ortholog_2_queryneighbors[ortho].append(neigbor)
            except KeyError:
                pass

        query_gene = query_genome_genes[window]
        other_genes = reply.context['o_md']
        for query_ortholog in query_gene['orthologs']:
            # assert that orthologs have the same type (===same color)
            self.assertIn(query_ortholog, other_genes)
        for ortholog in other_genes.values():
            for o_neighbor in ortholog['o_genes'].values():
                if not o_neighbor['o_type'] in ('blank', 'not found'):
                    for query_gene in ortholog_2_queryneighbors[o_neighbor['entryid']]:
                        if isinstance(o_neighbor['o_type'], list):
                            self.assertIn(query_gene['type'], o_neighbor['o_type'])
                        else:
                            self.assertEqual(query_gene['type'], o_neighbor['o_type'],
                                             'colors of {} disagrees with {}'
                                             .format(o_neighbor['entryid'], query_gene['entryid']))

    def test_colors_of_neighbors_various_windowsize(self):
        queries = 'YEAST00055', 'YEAST00056', 'ASHGO01345'
        windows_sizes = 4, 2, 6
        for query in queries:
            for window in windows_sizes:
                self.verify_colors(query, window)

    def test_many_to_many_links(self):
        """test that there is an gene that is orthologous to genes 1 and 4 in query gene. If it is, then there
        is a button element with class btn-5-0-
        TODO: make this test more stable"""
        query = 'SCHPO04241'
        reply = self.client.get(reverse('synteny', args=[query]))
        context = decode_replycontent(reply)
        self.assertIn('btn-0-4-', context)
        self.verify_colors(query, 4)


class SearchTester(TestCase):

    def query_server(self, query, **kwargs):
        url = reverse('search')
        args = {'query': query}
        args.update(kwargs)
        reply = self.client.get(url, data=args)
        return reply

    def test_unique_ids_resolve_directly(self):
        for query in ("PGTB2_SCHPO", "SPAC167.02", "O13948"):
            res = self.query_server(query)
            self.assertEqual(302, res.status_code, "ID '{}' did not resolve uniquely".format(query))
            self.assertTrue(res.url.startswith('/oma/info/'))

    def test_part_of_id(self):
        query = "TB2"
        reply = self.query_server(query)
        for target in json.loads(reply.context['data']):
            for xref in target['xrefs']:
                if query.lower() in xref['xref'].lower():
                    break
            else:
                self.assertTrue(False, "Couldn't find '{}' in search result {}".format(query, target))

    def test_sequence_search(self):
        s = "RSYKNSSAEGVLTGKGLNWGGSLIRPEAFGLVYYTQAMIDYATNGSFEGKRVTISGSGANVAQYAALKVIEVVSLSDSKGCIISETSEQIHD"
        res = self.client.post(reverse('search'), data={'query': s, 'type': 'sequence'})
        self.assertEqual(200, res.status_code)
        self.assertIn('DHE5_YEAST', [z['xrefid'] for z in json.loads(res.context['data'])])

    def test_sequence_in_lowercase(self):
        s = "RSYKNSSAEGVLTGKGLNWGGSLIRPEAF".lower()
        reply = self.query_server(s, type="sequence")
        self.assertIn('DHE5_YEAST', [z['xrefid'] for z in json.loads(reply.context['data'])])

    def test_numeric_group_search(self):
        gnr = 10
        res = self.query_server(gnr, type='group')
        self.assertEqual(302, res.status_code)
        self.assertEqual(reverse('omagroup', args=[gnr]), res.url)

    def test_search_species_name(self):
        queries = ["YEAST", "559292", "4890", "Saccharomyces cerevisiae", "Baker's yeast"]
        expected_code = "YEAST"
        for query in queries:
            reply = self.query_server(query, type="species")
            self.assertEqual(200, reply.status_code)
            self.assertIn('YEAST', [z['uniprot_species_code'] for z in json.loads(reply.context['data'])])



class TemplatetagTester(TestCase):

    def test_uniprot_seq_repr(self):
        self.maxDiff = None
        s = ("MTSEPEFQQAYDEIVSSVEDSKIFEKFPQYKKVLPIVSVPERIIQFRVTWENDNGEQEVAQGYRVQFNSAKGPYKGGLRF"
             "HPSVNLSILKFLGFEQIFKNALTGLDMGGGKGGLCVDLKGKSDNEIRRICYAFMRELSRHIGKDTDVPAGDIGVGGREIG"
             "YLFGAYRSYKNSWEGVLTGKGLNWGGSLIRPEATGFGLVYYTQAMIDYATNGKESFEGKRVTISGSGNVAQYAALKVIEL"
             "GGIVVSLSDSKGCIISETGITSEQIHDIASAKIRFKSLEEIVDEYSTFSESKMKYVAGARPWTHVSNVDIALPCATQNEV"
             "SGDEAKALVASGVKFVAEGANMGSTPEAISVFETARSTATNAKDAVWFGPPKAANLGGVAVSGLEMAQNSQKVTWTAERV"
             "DQELKKIMINCFNDCIQAAQEYSTEKNTNTLPSLVKGANIASFVMVADAMLDQGDVF")
        exp = ("MTSEPEFQQA YDEIVSSVED SKIFEKFPQY KKVLPIVSVP ERIIQFRVTW ENDNGEQEVA    60\n"
               "QGYRVQFNSA KGPYKGGLRF HPSVNLSILK FLGFEQIFKN ALTGLDMGGG KGGLCVDLKG   120\n"
               "KSDNEIRRIC YAFMRELSRH IGKDTDVPAG DIGVGGREIG YLFGAYRSYK NSWEGVLTGK   180\n"
               "GLNWGGSLIR PEATGFGLVY YTQAMIDYAT NGKESFEGKR VTISGSGNVA QYAALKVIEL   240\n"
               "GGIVVSLSDS KGCIISETGI TSEQIHDIAS AKIRFKSLEE IVDEYSTFSE SKMKYVAGAR   300\n"
               "PWTHVSNVDI ALPCATQNEV SGDEAKALVA SGVKFVAEGA NMGSTPEAIS VFETARSTAT   360\n"
               "NAKDAVWFGP PKAANLGGVA VSGLEMAQNS QKVTWTAERV DQELKKIMIN CFNDCIQAAQ   420\n"
               "EYSTEKNTNT LPSLVKGANI ASFVMVADAM LDQGDVF                            457\n")
        from oma.templatetags.oma_extras import uniprot_seq_repr
        self.assertEqual(uniprot_seq_repr(s), exp)
