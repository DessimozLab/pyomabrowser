from django.test import RequestFactory, TestCase

from .views import gateway


class GatewayRedirectTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _get(self, querystring):
        request = self.factory.get("/cgi-bin/gateway.pl", querystring)
        return gateway(request)

    # ---- Index -------------------------------------------------------
    def test_index(self):
        r = self._get({"f": "Index"})
        self.assertEqual(r.status_code, 301)
        self.assertEqual(r["Location"], "/")

    def test_no_f_defaults_to_index(self):
        r = self._get({})
        self.assertEqual(r["Location"], "/")

    # ---- DisplayEntry ------------------------------------------------
    def test_display_entry_info(self):
        r = self._get({"f": "DisplayEntry", "p1": "HUMAN00042", "p2": "info"})
        self.assertEqual(r["Location"], "/oma/info/HUMAN00042/")

    def test_display_entry_default_tab(self):
        r = self._get({"f": "DisplayEntry", "p1": "HUMAN00042"})
        self.assertEqual(r["Location"], "/oma/info/HUMAN00042/")

    def test_display_entry_orthologs(self):
        r = self._get({"f": "DisplayEntry", "p1": "HUMAN00042", "p2": "orthologs"})
        self.assertEqual(r["Location"], "/oma/vps/HUMAN00042/")

    def test_display_entry_fasta(self):
        r = self._get({"f": "DisplayEntry", "p1": "HUMAN00042", "p2": "fasta"})
        self.assertEqual(r["Location"], "/oma/vps/HUMAN00042/fasta/")

    def test_display_entry_homeologs(self):
        r = self._get({"f": "DisplayEntry", "p1": "WHEAT00001", "p2": "homeologs"})
        self.assertEqual(r["Location"], "/oma/homeologs/WHEAT00001/")

    def test_display_entry_unknown_tab(self):
        r = self._get({"f": "DisplayEntry", "p1": "HUMAN00042", "p2": "groups"})
        self.assertEqual(r["Location"], "/oma/home/")

    # ---- DisplayGroup ------------------------------------------------
    def test_display_group_list(self):
        r = self._get({"f": "DisplayGroup", "p1": "123"})
        self.assertEqual(r["Location"], "/oma/omagroup/123/members/")

    def test_display_group_align(self):
        r = self._get({"f": "DisplayGroup", "p1": "123", "p2": "Align"})
        self.assertEqual(r["Location"], "/oma/omagroup/123/msa/")

    # ---- GroupDownload / DownloadMSA ---------------------------------
    def test_group_download(self):
        r = self._get({"f": "GroupDownload", "p1": "456"})
        self.assertEqual(r["Location"], "/oma/omagroup/456/fasta/")

    def test_download_msa(self):
        r = self._get({"f": "DownloadMSA", "p1": "456"})
        self.assertEqual(r["Location"], "/oma/omagroup/456/msa/")

    # ---- DisplayOS ---------------------------------------------------
    def test_display_os(self):
        r = self._get({"f": "DisplayOS", "p1": "HUMAN"})
        self.assertEqual(r["Location"], "/oma/genome/HUMAN/info/")

    # ---- Search ------------------------------------------------------
    def test_search_db(self):
        r = self._get({"f": "SearchDb", "p1": "kinase"})
        self.assertIn("query=kinase", r["Location"])

    def test_search_seq_db(self):
        r = self._get({"f": "SearchSeqDb", "p1": "MGLSD"})
        self.assertIn("type=sequence", r["Location"])

    # ---- ServerTest --------------------------------------------------
    def test_server_test(self):
        r = self._get({"f": "ServerTest"})
        self.assertEqual(r["Location"], "/oma/vps/HUMAN00008/")

    # ---- Fallback ----------------------------------------------------
    def test_unknown_function(self):
        r = self._get({"f": "SomeLegacyThing"})
        self.assertEqual(r["Location"], "/oma/home/")
