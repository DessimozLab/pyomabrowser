from builtins import range
import math
from functools import wraps
from io import StringIO


logger = logging.getLogger(__name__)


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


def encode_domains_to_dict(seqlen, domains, domain_mapper):
    """return an dict structure of the given domains.

    The result can be serialized with json and is in the expected format
    for the domain_vis.js to be rendered.

    :param seqlen: the length of the protein sequence
    :param domains: a domain structure returned by
        :meth:`pyoma.browser.db.Database.get_domains`
    :param domain_mapper: an instance of :class:`pyoma.browser.db.DomainNameMapper`"""

    regions = []
    if len(domains) == 0:
        return {'length': seqlen,
                'regions': [{'name': 'n/a', 'source': 'n/a',
                             'location': "{}:{}".format(int(seqlen * .1), int(seqlen * .9))}]}

    for dom in domains:
        try:
            region = domain_mapper.get_info_dict_from_domainid(dom['DomainId'])
            region['location'] = dom['Coords'].decode()
            regions.append(region)
        except KeyError as e:
            logger.info('ignoring domain annotation: {}'.format(e))

    return {'length': seqlen, 'regions': regions}
