import math

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

