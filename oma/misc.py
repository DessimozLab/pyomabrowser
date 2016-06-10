from io import StringIO
import logging
import itertools
from future.moves.itertools import zip_longest


logger = logging.getLogger(__name__)


def as_fasta(seqs, headers=None):
    """format an iterable of sequences in fasta format.

    The sequences are written as they are, i.e. they are treated
    as plain strings, meaning no checking of symbols,...

    :param seqs: an iterable yielding the sequences.
    :param headers: an iterable yielding the headers, one per sequence. """
    if headers is None:
        headers = ("seq{}".format(i) for i in itertools.count(1))

    buf = StringIO()
    sentinel = object()
    for header, seq in zip_longest(headers, seqs, fillvalue=sentinel):
        if sentinel in (header, seq):
            raise ValueError(u"header and seqs do not have the same length")
        buf.write(u'>{}\n'.format(header))
        for k in range(0, len(seq), 80):
            buf.write(seq[k:k + 80])
            buf.write(u'\n')
        buf.write(u'\n')
    return buf.getvalue()


def encode_domains_to_dict(entry, domains, domain_mapper):
    """return an dict structure of the given domains.

    The result can be serialized with json and is in the expected format
    for the domain_vis.js to be rendered.

    :param seqlen: the length of the protein sequence
    :param domains: a domain structure returned by
        :meth:`pyoma.browser.db.Database.get_domains`
    :param domain_mapper: an instance of :class:`pyoma.browser.db.DomainNameMapper`"""

    regions = []
    seqlen = int(entry['SeqBufferLength'])
    seqid = entry['MD5ProteinHash'].decode()
    if len(domains) == 0:
        return {'length': seqlen,
                'seq_id': seqid,
                'regions': [{'name': 'n/a', 'source': 'n/a',
                             'location': "{}:{}".format(int(seqlen * .1), int(seqlen * .9))}]}

    for dom in domains:
        try:
            region = domain_mapper.get_info_dict_from_domainid(dom['DomainId'])
            region['location'] = dom['Coords'].decode()
            regions.append(region)
        except KeyError as e:
            logger.info('ignoring domain annotation: {}'.format(e))

    return {'length': seqlen, 'seq_id': seqid, 'regions': regions}
