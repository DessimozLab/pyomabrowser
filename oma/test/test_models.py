from oma import models, utils
from django.test import TestCase
from future.utils import with_metaclass
import sys


class ProteinEntryTests(TestCase):
    def test_init_from_enr(self):
        protein_entry = models.ProteinEntry.from_entry_nr(utils.db, 12)
        self.assertEqual(protein_entry.entry_nr, 12)
        try:
            protein_entry.canonicalid
        except AttributeError:
            self.assertTrue(False, 'entry not properly loaded')

    def test_lazy_eval_of_properties(self):
        protein_entry = models.ProteinEntry.from_entry_nr(utils.db, 12)
        self.assertNotIn('sequence', protein_entry.__dict__)
        seq = protein_entry.sequence
        self.assertIn('sequence', protein_entry.__dict__)

    def test_repr_of_ProteinEntry(self):
        protein_entry = models.ProteinEntry.from_entry_nr(utils.db, 12)
        if sys.version_info[0] >= 3 and sys.version_info[1] > 2:
            self.assertRegex("{!r}".format(protein_entry), r"<ProteinEntry\(12,.*\)")
        else:
            self.assertRegexpMatches("{!r}".format(protein_entry), r"<ProteinEntry\(12,.*\)")


class SingletonTests(TestCase):

    def test_singleton(self):
        class Foo(with_metaclass(models.Singleton, object)):
            def __init__(self):
                pass

        a = Foo()
        b = Foo()
        self.assertEqual(a, b)