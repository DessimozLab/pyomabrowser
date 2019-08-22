from .utils import id_mapper


def xref_order(request):
    # provide xref_order variable in every template
    return {'xref_order': id_mapper['Xref'].canonical_source_order()}

