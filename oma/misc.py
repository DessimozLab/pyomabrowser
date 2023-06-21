import functools
import hashlib
import os
import tempfile
from io import StringIO
import logging
import itertools
import tweepy
from django.conf import settings
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


def retrieve_from_uniprot_rest(endpoint):
    import json, requests
    url = "https://www.ebi.ac.uk/proteins/api/taxonomy/" + endpoint
    r = requests.get(url, headers={"Accept": "application/json"})
    if not r.ok:
        r.raise_for_status()
    return json.loads(r.text)


def genome_info_from_uniprot_rest(taxid):
    """retrieve some basic information about a genome given a
    taxonomy id. returns a dict with 'scientific_name',
    'mnemonic_code' and the lineage """
    os_data = retrieve_from_uniprot_rest("id/{:d}".format(taxid))
    lineage = retrieve_from_uniprot_rest("lineage/{:d}".format(taxid))
    header = {'scientific_name': os_data['scientificName'],
              'mnemonic_code': os_data['mnemonic']}
    if 'commonName' in os_data:
        header['common_name'] = os_data['commonName']
    lin = [z['scientificName'] for z in lineage['taxonomies']]
    while lin[-1] not in ('Eukaryota', 'Bacteria', 'Archaea'):
        lin.pop()
    lin.reverse()
    header['lineage'] = lin
    return header


def md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def handle_uploaded_file(fh, dir=None):
    if dir is not None:
        os.makedirs(dir, exist_ok=True)
    base, suffix = os.path.splitext(fh.name)
    with tempfile.NamedTemporaryFile(suffix=suffix, prefix=base, delete=False, dir=dir) as destination:
        for chunk in fh.chunks():
            destination.write(chunk)
    res = {'fname': destination.name, 'md5': md5(destination.name)}
    return res


def retrieve_last_tweets(nr_tweets=3):
    if settings.TWITTER_CONSUMER_KEY is None:
        return ["twitter not configured - no tweets found"]
    try:
        auth = tweepy.OAuthHandler(settings.TWITTER_CONSUMER_KEY, settings.TWITTER_CONSUMER_SECRET)
        auth.set_access_token(settings.TWITTER_ACCESS_TOKEN, settings.TWITTER_ACCESS_TOKEN_SECRET)

        api = tweepy.API(auth)

        public_tweets = api.user_timeline(user_id='@OMABrowser', exclude_replies=True,
                                          trim_user=True, include_rts=False)
        tweets = []
        for tweet in public_tweets[:nr_tweets]:
            text = tweet.text
            # replace t.co shortened URLs by true urls
            for url in sorted(tweet.entities['urls'], key=lambda x: x['indices'], reverse=True):
                text = (text[:url['indices'][0]] +
                        '<a href="' + url['expanded_url'] + '">' + url['expanded_url'] + '</a>' +
                        text[url['indices'][1]:])
            tweets.append(text)
    except (AttributeError, tweepy.TweepyException) as err:
        # attribute errors occur if TWITTER settings are not assigned
        tweets = ['Currently no tweets found']
    return tweets

@functools.lru_cache(maxsize=4)
def get_omastandalone_versions(latest=5):
    from pkg_resources import parse_version
    try:
        root = os.path.join(os.environ['DARWIN_BROWSER_SHARE'], 'standalone')
    except KeyError:
        logger.warning('Cannot determine root dir for downloads.')
        root = "standalone"
    logger.debug('params for oma standalone version search: root={}'.format(root))
    try:
        releases = [f[4:-4] for f in os.listdir(root) if f.startswith('OMA.') and f.endswith('.tgz')]
    except IOError:
        return []
    rel_v = list(map(parse_version, releases))
    return list(map(str, sorted(rel_v, reverse=True)[:latest]))
