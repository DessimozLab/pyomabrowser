from django.http.request import urlencode

from django.http import HttpResponseBadRequest, HttpResponse
from django.template.loader import render_to_string
from django.shortcuts import reverse
from oma import utils
from pyoma.browser import search
from xml.etree import ElementTree


# Create your views here.
def expasy_search(request):
    if request.method == 'GET':
        try:
            query = request.GET['query']
            typ = request.GET['type']
            res_format = request.GET.get('format', 'xml')
        except KeyError:
            context = {"errortype": "input error", "message": "query and type argument are required input fields"}
            content = render_to_string("expasy-error.xml", context, request)
            return HttpResponseBadRequest(content, "application/xml")

        if typ == "text" and utils.db.seq_search.contains_only_valid_chars(query):
            typ = "AA"

        if typ == "AA" and len(query) > 5:
            seq_term = search.SequenceSearch(utils.db, query)
            res = seq_term.search_entries()
            if len(res) > 1:
                url = reverse('search') + "?" + urlencode({"type": "Entry_sequence", "query": query})
            else:
                url = reverse('entry_info', args=[res[0].oma_id])
            context = {"count": len(res), "url": request.build_absolute_uri(url)}
        else:
            ref_term = search.XRefSearch(utils.db, query, max_matches=30)
            if ref_term.estimated_occurrences < 30:
                res = ref_term.search_entries()
                oma_ids = set(p.get_main_isoform().oma_id for p in res)
                if len(oma_ids) == 1:
                    url = reverse('entry_info', args=[oma_ids.pop()])
                    count = 1
                else:
                    url = reverse('search', ) + "?" + urlencode({"query": query})
                    count = len(res)
            else:
                url = reverse('search') + "?" + urlencode({"query": query})
                count = ref_term.estimated_occurrences
            context = {"count": count, "url": request.build_absolute_uri(url)}

        if res_format == "xml":
            content = render_to_string("expasy-result.xml", context, request)
            return HttpResponse(content, "application/xml")
        elif res_format == "tsv":
            content = "{count}\t{url}\n".format(**context).encode('utf-8')
            return HttpResponse(content, "text/tsv")
        else:
            context = {"type": "input error", "message": "format value ({}) is unknown".format(res_format)}
            content = render_to_string("expasy-error.xml", context, request)
            return HttpResponseBadRequest(content, "application/xml")
