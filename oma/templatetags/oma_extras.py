from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()

@register.filter
@stringfilter
def uniprot_seq_repr(value):
    len_seq = len(value)
    res = []
    for i in range(0, len_seq, 60):
        for k in range(i, i+60, 10):
            res.extend((value[k:k+10], ' '))
        padding = 5
        if i+60 > len_seq:
            padding += i+60-len_seq
        res.extend(('{:{pad}d}'.format(min(i+60, len_seq), pad=padding), '\n'))
    return "".join(res)

