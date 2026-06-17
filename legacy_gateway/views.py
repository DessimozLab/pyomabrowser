"""
Replacement for cgi-bin/gateway.pl + Darwin backend.

Accepts the same ?f=FUNCTION&p1=VALUE&p2=VALUE... query-string format
and issues permanent redirects to the equivalent new Django URLs.

Redirect targets were taken verbatim from the redirect() calls in
EntryDisplay.drw, GroupDisplay.drw, and ServerMain.drw.
"""

from urllib.parse import urlencode
from django.urls import reverse
from django.http import HttpResponsePermanentRedirect


def _params(request):
    """Return positional parameters p1, p2, … as a list (may be empty)."""
    result = []
    i = 1
    while True:
        v = request.GET.get(f"p{i}")
        if v is None:
            break
        result.append(v)
        i += 1
    return result


def gateway(request):
    f = request.GET.get("f", "Index")
    p = _params(request)

    target = _resolve(f, p)
    return HttpResponsePermanentRedirect(target)


def _resolve(f, p):  # noqa: C901 (intentionally flat dispatch table)
    if f == "Index":
        return "/"

    # ------------------------------------------------------------------
    # Entry display  (EntryDisplay.drw: omaDisplayEntry)
    # ------------------------------------------------------------------
    if f == "DisplayEntry":
        entry_id = p[0] if p else ""
        tab = p[1] if len(p) > 1 else "info"
        if tab in ("info", ""):
            return reverse('entry_info', args=[entry_id])
        if tab in ("orthologs", ):
            return reverse('pairs', args=[entry_id])
        if tab in ("fasta", ):
            return reverse('pairs_fasta', args=[entry_id])
        if tab == "homeologs":
            return reverse('pair_homeologs', args=[entry_id])
        return reverse("home")

    # ------------------------------------------------------------------
    # Group display  (GroupDisplay.drw)
    # ------------------------------------------------------------------
    if f == "DisplayGroup":
        og = p[0] if p else ""
        tab = p[1] if len(p) > 1 else "List"
        if tab == "Align":
            return reverse('omagroup_align', args=[og])
        return reverse('omagroup_members', args=[og])

    if f == "GroupDownload":
        og = p[0] if p else ""
        return reverse('omagroup-fasta', args=[og])

    if f == "DownloadMSA":
        og = p[0] if p else ""
        return reverse('omagroup_align', args=[og])

    # ------------------------------------------------------------------
    # Genome / species  (ServerMain.drw: omaDisplayOS)
    # ------------------------------------------------------------------
    if f == "DisplayOS":
        os_code = p[0] if p else ""
        return reverse('genome_info', args=[os_code])

    # ------------------------------------------------------------------
    # ServerTest
    # ------------------------------------------------------------------
    if f == "ServerTest":
        return reverse('pairs', args=['HUMAN00008'])

    # ------------------------------------------------------------------
    # Search  (new Django search view)
    # ------------------------------------------------------------------
    if f == "SearchDb":
        query = p[0] if p else ""
        return reverse('search') + '?' + urlencode({"query": query})

    if f == "SearchSeqDb":
        query = p[0] if p else ""
        return reverse('search') + '?' + urlencode({"query": query, "type": "sequence"})

    # ------------------------------------------------------------------
    # Everything else falls back to the home page
    # ------------------------------------------------------------------
    return reverse('home')
