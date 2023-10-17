from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView
from django.views.generic.base import ContextMixin
from .models import TaxonMapperService, Taxon


# Create your views here.
class TaxonomyMapView(TemplateView, ContextMixin):
    template_name = "taxmap/taxonomymap.html"

    def get_context_data(self, taxon, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            tax = TaxonMapperService()[int(taxon)]
            context['taxon'] = [tax]
            context['many'] = False
        except KeyError:
            raise Http404(f"Unknown taxid {taxon}")
        except ValueError:
            tax = TaxonMapperService().search(taxon)
            if len(tax) == 0:
                raise Http404(f"Unknown taxid {taxon}")
            elif isinstance(tax, Taxon):
                context['taxon'] = [tax]
                context['many'] = False
            elif isinstance(tax, dict):
                context['taxon'] = list(tax.keys())
                context['many'] = len(context['taxon']) > 1
            else:
                raise Exception(f"Unexpected instance {tax}")
        context['query'] = taxon
        return context
