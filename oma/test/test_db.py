from __future__ import print_function, absolute_import, division
from django.test import TestCase
import numpy
from ..utils import tax, db
import json
import collections

class TaxonomyTest(TestCase):
    def setUp(self):
        self.tax = tax;

    def test_parents(self):
        lin = [x['Name'].decode() for x in tax.get_parent_taxa(284811)]
        self.assertEqual(lin, ['Ashbya gossypii (strain ATCC 10895 / CBS 109.51 / FGSC 9923 / NRRL Y-1056)',
                               'Eremothecium', 'Saccharomycetaceae', 'Saccharomycetales',
                               'Saccharomycetes', 'Saccharomycotina', 'saccharomyceta',
                               'Ascomycota', 'Dikarya', 'Fungi', 'Opisthokonta', 'Eukaryota'])

    def test_newick(self):
        member = frozenset([tax._taxon_from_numeric(x)['Name'] for x in tax.tax_table['NCBITaxonId']])
        newick = tax.newick(member)
        expected = '(("Schizosaccharomyces pombe (strain 972 / ATCC 24843)",("Ashbya gossypii (strain ATCC 10895 / CBS 109.51 / FGSC 9923 / NRRL Y-1056)","Saccharomyces cerevisiae (strain ATCC 204508 / S288c)")"Saccharomycetaceae")"Ascomycota","Plasmodium falciparum (isolate 3D7)")"Eukaryota"'
        self.assertEqual(expected, newick)

    def test_phylogeny(self):
        member = frozenset([tax._taxon_from_numeric(x)['Name'] for x in tax.tax_table['NCBITaxonId']])
        phylo = tax.phylogeny(member)
        json_phylo = json.dumps(phylo)
        expected = '{"name":"Eukaryota","children":[{"name":"Ascomycota", "children":[' \
                     '{"name": "Schizosaccharomyces pombe (strain 972 / ATCC 24843)"},' \
                     '{"name": "Saccharomycetaceae", "children":[' \
                       '{"name": "Ashbya gossypii (strain ATCC 10895 / CBS 109.51 / FGSC 9923 / NRRL Y-1056)"},' \
                       '{"name": "Saccharomyces cerevisiae (strain ATCC 204508 / S288c)"}]' \
                     '}]}, {"name": "Plasmodium falciparum (isolate 3D7)"}]}'
        self.assertJSONEqual(expected, json_phylo)


class DatabaseTest(TestCase):
    def test_lex_range_of_hogs(self):
        cases = [[u'HOG22.1a', (b'HOG22.1a', b'HOG22.1b')],
                 ['HOG00001', (b'HOG00001', b'HOG00002')],
                ]
        for case in cases:
            hog, expected = case
            self.assertEqual(expected, db._hog_lex_range(hog))

    def test_fam_member(self):
        memb = db.member_of_fam(1)
        self.assertEqual(2, len(memb))

    def test_hogids_at_level(self):
        cases = [[(2, 'Ascomycota'), numpy.array([b'HOG:0000002'])],
                 [(2, 'Saccharomyces cerevisiae (strain ATCC 204508 / S288c)'), numpy.array([b'HOG:0000002.2a', b'HOG:0000002.2b'])]]

        for case in cases:
            args, expected = case
            levels = db.get_subhogids_at_level(*args)
            self.assertTrue(numpy.array_equal(expected, levels),
                            'test of tes_hogids_at_level failed for {}: {}'.format(args, levels))