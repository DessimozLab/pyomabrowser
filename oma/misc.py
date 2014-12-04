import math
from io import BytesIO

def downloadURL_hog(fam):
    return '/All/HOGs/{0:04d}/HOG{1:07d}.orthoxml'.format(
            int(math.ceil(fam/500.0)), fam)

def format_sciname(sci, short=False):
    p = set(map(lambda x:sci.find(x), ['(','serogroup','serotype','serovar',
                                         'biotype','subsp','pv.','bv.']))
    if sci.startswith('Escherichia coli'):
       p.add(sci.find('O'))
    p.discard(-1)
    p = min(p) if len(p)>0 else len(sci)
    return {'species': sci[0:p], 'strain':sci[p:]}

def as_fasta(seqs, headers=None):
    if headers is None:
        headers =['seq{}'.format(i+1) for i in range(len(seqs))]
    if len(seqs) != len(headers):
        raise ValueError('number of headers and sequences does not match')

    buf = BytesIO()
    for i, seq in enumerate(seqs):
        buf.write('> {}\n'.format(headers[i]))
        for k in range(0,len(seq),80):
            buf.write(seq[k:k+80])
            buf.write('\n')
        buf.write('\n')
    return buf.getvalue()
