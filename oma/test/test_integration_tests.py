import json
from django.test import TestCase
from django.core.urlresolvers import reverse
import re
import collections


def decode_replycontent(reply):
    content_type = reply['Content-Type']
    match = re.search('charset=(?P<encoding>[A-Za-z0-9-]+)', content_type)
    enc = 'ascii' if match is None else match.group('encoding')
    return reply.content.decode(enc)


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
    def test_simple_fam_encoding(self):
        exp_tree = {'name': 'Eukaryota',
                    'children': [{'name': 'Ascomycota',
                                  'children': [{'name': 'Schizosaccharomyces pombe (strain 972 / ATCC 24843)'},
                                               {'name': 'Saccharomyces cerevisiae (strain ATCC 204508 / S288c)'}]},
                                 {'name': 'Plasmodium falciparum (isolate 3D7)'}]}
        reply = self.client.get(reverse('hog_vis', args=['YEAST12']))
        phylo = json.loads(reply.context['species_tree'])
        self.assertDictEqual(exp_tree, phylo)

        per_species = json.loads(reply.context['per_species'])
        for spec, lev, cnts in [('Saccharomyces cerevisiae (strain ATCC 204508 / S288c)', 'Eukaryota', [2]),
                                ('Saccharomyces cerevisiae (strain ATCC 204508 / S288c)', 'Saccharomyces cerevisiae (strain ATCC 204508 / S288c)', [1,1]),
                                ]:
            nr_genes_per_subhog = [len(z) for z in per_species[spec][lev]]
            self.assertEqual(nr_genes_per_subhog, cnts, 'missmatch of subhogs at {}/{}: {} vs {}'
                             .format(spec, lev, nr_genes_per_subhog, cnts))


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


