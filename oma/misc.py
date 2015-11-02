from builtins import range
import math
from functools import wraps
from io import StringIO


def format_sciname(sci, short=False):
    p = set([sci.find(x) for x in ['(','serogroup','serotype','serovar',
                                         'biotype','subsp','pv.','bv.']])
    if sci.startswith('Escherichia coli'):
       p.add(sci.find('O'))
    p.discard(-1)
    p = min(p) if len(p)>0 else len(sci)
    return {'species': sci[0:p], 'strain':sci[p:]}


def as_fasta(seqs, headers=None):
    if headers is None:
        headers = ['seq{}'.format(i+1) for i in range(len(seqs))]
    if len(seqs) != len(headers):
        raise ValueError('number of headers and sequences does not match')

    buf = StringIO()
    for i, seq in enumerate(seqs):
        buf.write(u'> {}\n'.format(headers[i]))
        for k in range(0, len(seq), 80):
            buf.write(seq[k:k+80])
            buf.write(u'\n')
        buf.write(u'\n')
    return buf.getvalue()


class LazyProperty(object):
    """Decorator to evaluate a property only on access.

    Compute the attribute value and caches it in the instance.
    Python Cookbook (Denis Otkidach) http://stackoverflow.com/users/168352/denis-otkidach
    This decorator allows you to create a property which can be computed once and
    accessed many times."""
    def __init__(self, method, name=None):
        # record the unbound-method and the name
        self.method = method
        self.name = name or method.__name__
        self.__doc__ = method.__doc__

    def __get__(self, inst, cls):
        if inst is None:
            return self
        # compute, cache and return the instance's attribute value
        result = self.method(inst)
        # setattr redefines the instance's attribute so this doesn't get called again
        setattr(inst, self.name, result)
        return result

