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
        nr_vps = reply.context['nr_vps']
        self.assertGreater(nr_vps, 0)
        api_url = reply.context['table_data_url']
        self.assertIsNotNone(api_url)
        api_data = self.client.get(api_url)
        self.assertEqual(api_data.status_code, 200)
        api_data = json.loads(decode_replycontent(api_data))
        self.assertGreaterEqual(len(api_data), nr_vps)

    def test_inexistant_query_genome(self):
        query = 'ECOLI00411'
        reply = self.client.get(reverse('pairs', args=[query]))
        self.assertEqual(reply.status_code, 404)


class HogFastaView_Test(TestCase):
    def get_fasta_and_verify_sequences_and_nr_members(self, query, level, seqs, nr_expected_members):
        if isinstance(seqs, str):
            seqs = [seqs]
        reply = self.client.get(reverse('hog_fasta', args=[query, level]))
        self.assertEqual(reply.status_code, 200)
        content = reply.content.decode()
        self.assertEqual(content.count('>'), nr_expected_members)
        for seq in seqs:
            self.assertIn(seq, content, 'sequence {!r} not in reply')

    def test_query_sequence_in_result_at_fungi(self):
        self.get_fasta_and_verify_sequences_and_nr_members('HOG:0000002', 'Fungi',
                                                           ['MTSEPEFQQAYDEIVSSVEDSKIF', 'KRVLPIISIPERVLEFRVTWEDD'], 3)

    def test_query_sequence_in_result_at_eukaryota(self):
        self.get_fasta_and_verify_sequences_and_nr_members('HOG:0000002', 'Eukaryota',
                                                           ['MILYSCVVCFIVFVFHVKAYSKNKVLKYAK',
                                                            'KRVLPIISIPERVLEFRVTWEDD'], 5)


class HogView_Test(TestCase):
    def test_orthoxml(self):
        """Test retrieval of an individual orthoxml"""
        query = "HOG:0000002"
        reply = self.client.get(reverse('hogs_orthoxml', args=[query]))
        self.assertEqual(reply.status_code, 200)
        content = decode_replycontent(reply)
        self.assertIn(query, content)
        self.assertIn('orthoXML', content)

    def test_hog_by_proteinid_redirect(self):
        query, exp_hog = "YEAST00012", "HOG:0000002"
        reply = self.client.get(reverse('hog_table_from_entry', args=[query]))
        self.assertEqual(reply.status_code, 302)
        self.assertIn(exp_hog, reply.url)

    def test_hog_success_page(self):
        query = "HOG:0000002"
        reply = self.client.get(reverse('hog_table', args=[query, 'Eukaryota']), follow=True)
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(len(reply.context['hog'].members), 5)
        self.assertIn(query, decode_replycontent(reply))

    def test_basehog_without_orthologs(self):
        """test that redirect to vps page if not part of a hog"""
        reply = self.client.get(reverse('hog_table_from_entry', args=['YEAST10']), follow=True)
        self.assertEqual(reply.status_code, 200)
        self.assertIn('vps', reply.redirect_chain[0][0])

    def test_invalid_level(self):
        """test that an invalid level (level not belonging to species) will return an error message"""
        reply = self.client.get(reverse('hog_table', args=["HOG:0000002", 'Mammalia']))
        self.assertEqual(reply.status_code, 404)


class HogVisViewTest(TestCase):
    def test_return_right_orthoxml_link(self):
        query, member_prot = 'HOG:0000002', "YEAST00012"
        reply = self.client.get(reverse('hog_viewer', args=[query]))
        self.assertEqual(reply.status_code, 200)
        #self.assertTemplateUsed(reply, "hog_iHam.html")
        expected_orthoxml_url = reverse('hogs_orthoxml', args=[query])
        expected_species_url = '/All/speciestree.nwk'
        self.assertIn('url: "{}"'.format(expected_orthoxml_url).encode('utf-8'), reply.content)
        self.assertIn('url: "{}"'.format(expected_species_url).encode('utf-8'), reply.content)

        # test that orthoxml has query gene
        orthoxml = self.client.get(expected_orthoxml_url)
        self.assertEqual(orthoxml.status_code, 200)
        self.assertIn('protId="{}"'.format(member_prot).encode('utf-8'), orthoxml.content)

    def test_access_singleton_protein(self):
        query = 'YEAST11'  # this protein is not part of any HOG
        reply = self.client.get(reverse('hog_viewer', args=[query]))
        self.assertEqual(404, reply.status_code)


class TokenSearchTester(TestCase):
    def query_server(self, query, **kwargs):
        url = reverse('search_token')
        args = {'query': query}
        args.update(kwargs)
        data = {'hidden_query': json.dumps([args])}
        reply = self.client.post(url, data=data)
        return reply

    def query_multiple_tokens(self, tokens):
        url = reverse('search_token')
        data = {'hidden_query': json.dumps(tokens)}
        reply = self.client.post(url, data=data)
        return reply

    def test_resolve_unique_ids(self):
        for query in ("PGTB2_SCHPO", "SPAC167.02", "O13948"):
            res = self.query_server(query=query, prefix='description', type='Protein')
            self.assertEqual(302, res.status_code, "ID '{}' did not resolve uniquely".format(query))
            self.assertTrue(res.url.startswith('/oma/vps/'))

    def test_search_species_name(self):
        queries = ["YEAST", "559292", "4890", "Saccharomyces cerevisiae", "Baker's yeast"]
        expected_code = "YEAST"
        for query in queries:
            with self.subTest(query=query):
                reply = self.query_server(query, prefix="species", type="Taxon")
                if reply.status_code == 302:
                    self.assertEqual(reply.url, f"/oma/genome/{expected_code}/info/")
                else:
                    self.assertEqual(200, reply.status_code)
                    self.assertIn('YEAST', [z['uniprot_species_code'] for z in json.loads(reply.context['data_genomes'])])

    def test_sequence_search(self):
        queries = ("RSYKNSSAEGVLTGKGLNWGGSLIRPEAFGLVYYTQAMIDYATNGSFEGKRVTISGSGANVAQYAALKVIEVVSLSDSKGCIISETSEQIHD",
                   "RSYKNSSAEGVLTGKGLNWGGSLIRPEAF".lower())
        for query in queries:
            with self.subTest(query=query):
                res = self.query_server(query=query, prefix="sequence", type="Protein")
                self.assertEqual(200, res.status_code)
                self.assertIn('DHE5_YEAST', [z['xrefid'] for z in json.loads(res.context['data_entry'])])

    def test_part_of_id(self):
        query = "TB2"
        reply = self.query_server(query, prefix="xref", type="Protein")
        for target in json.loads(reply.context['data_entry']):
            for xref in target['xrefs']:
                if query.lower() in xref['xref'].lower():
                    break
            else:
                self.assertTrue(False, "Couldn't find '{}' in search result {}".format(query, target))

    def test_numeric_group_search(self):
        gnr = 10
        res = self.query_server(gnr, type='OMA_Group', prefix="og")
        self.assertEqual(302, res.status_code)
        self.assertEqual(reverse('omagroup_members', args=[gnr]), res.url)

    def test_two_species_terms(self):
        res = self.query_multiple_tokens([{'query': "Saccharomyces", "prefix": "species", "type": "Taxon"},
                                          {'query': "Fungi", "prefix": "species", "type": "Taxon"},
                                         ])
        self.assertEqual(200, res.status_code)
        genome_data = json.loads(res.context['data_genomes'])
        self.assertIn('YEAST', [z['uniprot_species_code'] for z in genome_data])


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
