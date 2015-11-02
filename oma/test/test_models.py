from oma import models
from django.test import TestCase


class ProteinEntry_Tests(TestCase):
    def test_init_from_enr(self):
        protein_entry = models.ProteinEntry.from_entry_nr(12)
        self.assertEqual(protein_entry.entry_nr, 12)
        try:
            protein_entry.canonicalid
        except AttributeError:
            self.assertTrue(False, 'entry not properly loaded')

    def test_lazy_eval_of_properties(self):
        protein_entry = models.ProteinEntry.from_entry_nr(12)
        self.assertNotIn('sequence', protein_entry.__dict__)
        seq = protein_entry.sequence
        self.assertIn('sequence', protein_entry.__dict__)

    def test_repr_of_ProteinEntry(self):
        protein_entry = models.ProteinEntry.from_entry_nr(12)
        self.assertRegex("{!r}".format(protein_entry), r"<ProteinEntry\(12,.*\)")