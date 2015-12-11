from builtins import range
import math
from functools import wraps
from io import StringIO




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




