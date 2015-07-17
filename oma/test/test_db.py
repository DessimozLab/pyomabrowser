from django.test import TestCase
from django.core.urlresolvers import reverse
import re

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
                        ['MILYSCVVCFIVFVFHVKAYSKNKVLKYAK', 'KRVLPIISIPERVLEFRVTWEDD'], 5)


class HogView_Test(TestCase):

    def decode_replycontent(self, reply):
        content_type = reply['Content-Type']
        match = re.search('charset=(?P<encoding>[A-Za-z0-9-]+)', content_type)
        enc = 'ascii' if match is None else match.group('encoding')
        return reply.content.decode(enc)

    def test_orthoxml(self):
        query = 'YEAST00012'
        reply = self.client.get(reverse('hogs_orthoxml', args=[query]))
        self.assertEqual(reply.status_code, 200)
        content = self.decode_replycontent(reply)
        self.assertIn(query, content)
        self.assertIn('orthoXML', content)

    def test_hog_success_page(self):
        query = 'YEAST00012'
        reply = self.client.get(reverse('hogs', args=[query, 'Eukaryota']))
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(len(reply.context['hog_members']), 5)
        self.assertIn(query, self.decode_replycontent(reply))

    def test_basehog_without_orthologs(self):
        """test that page returns doesn't belong to any hog message"""
        reply = self.client.get(reverse('hogs', args=['YEAST10']))
        self.assertEqual(reply.status_code, 200)
        self.assertIn("not part of any hierarchical orthologous group", self.decode_replycontent(reply))