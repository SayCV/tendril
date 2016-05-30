# Copyright (C) 2015 Chintalagiri Shashank
#
# This file is part of Tendril.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
The WWW Utils Module (:mod:`tendril.utils.www`)
===============================================

This module provides utilities to deal with the internet. All application code
should access the internet through this module, since this where support for
proxies and caching is implemented.

.. rubric:: Main Provided Elements

.. autosummary::

    urlopen
    get_soup
    get_soup_requests
    cached_fetcher
    get_session
    get_soap_client

This module uses the following configuration values from
:mod:`tendril.utils.config`:

.. rubric:: Network Proxy Settings

- :data:`tendril.utils.config.NETWORK_PROXY_TYPE`
- :data:`tendril.utils.config.NETWORK_PROXY_IP`
- :data:`tendril.utils.config.NETWORK_PROXY_PORT`
- :data:`tendril.utils.config.NETWORK_PROXY_USER`
- :data:`tendril.utils.config.NETWORK_PROXY_PASS`

.. rubric:: Caching

- :data:`tendril.utils.config.ENABLE_REDIRECT_CACHING`
  Whether or not redirect caching should be used.

Redirect caching speeds up network accesses by saving ``301`` and ``302``
redirects, and not needing to get the correct URL on a second access. This
redirect cache is stored as a pickled object in the ``INSTANCE_CACHE``
folder. The effect of this caching is far more apparent when a replicator
cache is also used.

This module also provides the :class:`WWWCachedFetcher` class,
an instance of which is available in :data:`cached_fetcher`, which
is subsequently used by :func:`get_soup` and any application code
that wants cached results.

Overall, caching should look something like this :

- WWWCacheFetcher provides short term (~5 days)
  caching, aggressively caching whatever goes through it. This
  caching is NOT HTTP1.1 compliant. In case HTTP1.1 compliant
  caching is desired, use the requests based implementation
  instead or use an external http-replicator like caching proxy.

- RedirectCacheHandler is something of a special case, handling
  redirects which otherwise would be incredibly expensive.
  Unfortunately, this layer is also the dumbest cacher, and
  does not expire anything, ever. To 'invalidate' something in
  this cache, the entire cache needs to be nuked. It may be
  worthwhile to consider moving this to redis instead.

.. todo::
    Consider replacing uses of urllib/urllib2 backend with
    :mod:`requests` and simplify this module. Currently, the
    cache provided with the ``requests`` implementation here
    is the major bottleneck.

"""

from __future__ import print_function

from .config import NETWORK_PROXY_TYPE
from .config import NETWORK_PROXY_IP
from .config import NETWORK_PROXY_PORT
from .config import NETWORK_PROXY_USER
from .config import NETWORK_PROXY_PASS

from .config import ENABLE_REDIRECT_CACHING
from .config import INSTANCE_CACHE

from bs4 import BeautifulSoup

from six.moves.urllib.request import HTTPRedirectHandler
from six.moves.urllib.request import ProxyHandler
from six.moves.urllib.request import HTTPHandler, HTTPSHandler
from six.moves.urllib.request import build_opener
from six.moves.urllib.error import HTTPError, URLError

import os
import six
import time

import atexit
import tempfile
import codecs
from hashlib import md5

import warnings
import logging
import requests
try:
    import cPickle as pickle
except ImportError:
    import pickle
from cachecontrol import CacheControlAdapter
from cachecontrol.caches import FileCache
from cachecontrol.heuristics import ExpiresAfter

from suds.client import Client
from suds.transport.http import HttpAuthenticated
from suds.transport.http import HttpTransport

from fs.opener import fsopendir
from fs.utils import movefile
from tendril.utils.fsutils import temp_fs
from tendril.utils import log
logger = log.get_logger(__name__, log.INFO)

logging.getLogger('cachecontrol.controller').setLevel(logging.INFO)
logging.getLogger('requests.packages.urllib3.connectionpool').\
    setLevel(logging.INFO)

logging.getLogger('suds.xsd.query').setLevel(logging.INFO)
logging.getLogger('suds.xsd.sxbasic').setLevel(logging.INFO)
logging.getLogger('suds.xsd.schema').setLevel(logging.INFO)
logging.getLogger('suds.xsd.sxbase').setLevel(logging.INFO)
logging.getLogger('suds.metrics').setLevel(logging.INFO)
logging.getLogger('suds.wsdl').setLevel(logging.INFO)
logging.getLogger('suds.client').setLevel(logging.INFO)
logging.getLogger('suds.resolver').setLevel(logging.INFO)
logging.getLogger('suds.umx.typed').setLevel(logging.INFO)
logging.getLogger('suds.mx.literal').setLevel(logging.INFO)
logging.getLogger('suds.mx.core').setLevel(logging.INFO)
logging.getLogger('suds.transport.http').setLevel(logging.INFO)

WWW_CACHE = os.path.join(INSTANCE_CACHE, 'soupcache')
REQUESTS_CACHE = os.path.join(INSTANCE_CACHE, 'requestscache')
SOAP_CACHE = os.path.join(INSTANCE_CACHE, 'soapcache')


def _get_http_proxy_url():
    """
    Constructs the proxy URL for HTTP proxies from relevant
    :mod:`tendril.utils.config` Config options, and returns the URL string
    in the form:

        ``http://[NP_USER:NP_PASS@]NP_IP[:NP_PORT]``

    where NP_xxx is obtained from the :mod:`tendril.utils.config` ConfigOption
    NETWORK_PROXY_xxx.
    """
    if NETWORK_PROXY_USER is None:
        proxyurl_http = 'http://' + NETWORK_PROXY_IP
    else:
        proxyurl_http = 'http://{0}:{1}@{2}'.format(NETWORK_PROXY_USER,
                                                    NETWORK_PROXY_PASS,
                                                    NETWORK_PROXY_IP)
    if NETWORK_PROXY_PORT:
        proxyurl_http += ':' + NETWORK_PROXY_PORT
    return proxyurl_http


def strencode(string):
    """
    This function converts unicode strings to ASCII, using python's
    :func:`str.encode`, replacing any unicode characters present in the
    string. Unicode characters which Tendril expects to see in web content
    related to it are specifically replaced first with ASCII characters
    or character sequences which reasonably reproduce the original meanings.

    :param string: unicode string to be encoded.
    :return: ASCII version of the string.

    .. warning::
        This function is marked for deprecation by the general (but gradual)
        move towards ``unicode`` across tendril.

    """
    nstring = ''
    for char in string:
        if char == u'\u00b5':
            char = 'u'
        if char == u'\u00B1':
            char = '+/-'
        nstring += char
    return nstring.encode('ascii', 'replace')


REDIR_CACHE_FILE = os.path.join(INSTANCE_CACHE, 'redirects.p')

try:
    with open(REDIR_CACHE_FILE, "rb") as rdcf:
        redirect_cache = pickle.load(rdcf)
    logger.info('Loaded Redirect Cache from file')
except IOError:
    redirect_cache = {}
    logger.info('Created new Redirect Cache')


def dump_redirect_cache():
    """
    Called during python interpreter shutdown, this function dumps the
    redirect cache to the file system.
    """
    if DUMP_REDIR_CACHE_ON_EXIT:
        with open(REDIR_CACHE_FILE, 'wb') as f:
            pickle.dump(redirect_cache, f, protocol=2)
        logger.info('Dumping Redirect Cache to file')

DUMP_REDIR_CACHE_ON_EXIT = True

if ENABLE_REDIRECT_CACHING is True:
    atexit.register(dump_redirect_cache)


class CachingRedirectHandler(HTTPRedirectHandler):
    """
    This handler modifies the behavior of
    :class:`urllib2.HTTPRedirectHandler`, resulting in a HTTP ``301`` or
    ``302`` status to be included in the ``result``.

    When this handler is attached to a ``urllib2`` opener, if the opening of
    the URL resulted in a redirect via HTTP ``301`` or ``302``, this is
    reported along with the result. This information can be used by the opener
    to maintain a redirect cache.
    """
    def http_error_301(self, req, fp, code, msg, headers):
        """
        Wraps the :func:`urllib2.HTTPRedirectHandler.http_error_301` handler,
        setting the ``result.status`` to ``301`` in case a http ``301`` error
        is encountered.
        """
        result = HTTPRedirectHandler.http_error_301(
            self, req, fp, code, msg, headers)
        result.status = code
        return result

    def http_error_302(self, req, fp, code, msg, headers):
        """
        Wraps the :func:`urllib2.HTTPRedirectHandler.http_error_302` handler,
        setting the ``result.status`` to ``302`` in case a http ``302`` error
        is encountered.
        """
        result = HTTPRedirectHandler.http_error_302(
            self, req, fp, code, msg, headers)
        result.status = code
        return result


def get_actual_url(url):
    # warnings.warn("get_actual_url() is a part of Redirect caching and is "
    #               "deprecated.", DeprecationWarning)
    if not ENABLE_REDIRECT_CACHING:
        return url
    else:
        while url in redirect_cache.keys():
            url = redirect_cache[url]
        return url


def _test_opener(openr):
    """
    Tests an opener obtained using :func:`urllib2.build_opener` by attempting
    to open Google's homepage. This is used to test internet connectivity.
    """
    try:
        openr.open('http://www.google.com', timeout=5)
        return True
    except URLError:
        return False


def _create_opener():
    """
    Creates an opener for the internet.

    It also attaches the :class:`CachingRedirectHandler` to the opener and
    sets its User-agent to ``Mozilla/5.0``.

    If the Network Proxy settings are set and recognized, it creates the
    opener and attaches the proxy_handler to it. The opener is tested and
    returned if the test passes.

    If the test fails an opener without the proxy settings is created instead
    and is returned instead.
    """
    use_proxy = False
    proxy_handler = None

    if NETWORK_PROXY_TYPE == 'http':
        use_proxy = True
        proxyurl = _get_http_proxy_url()
        proxy_handler = ProxyHandler({'http': proxyurl,
                                      'https': proxyurl})
    if use_proxy:
        openr = build_opener(HTTPHandler(), HTTPSHandler(),
                             proxy_handler, CachingRedirectHandler)
    else:
        openr = build_opener(HTTPSHandler(), HTTPSHandler(),
                             CachingRedirectHandler)
    openr.addheaders = [('User-agent', 'Mozilla/5.0')]
    if _test_opener(openr) is True:
        return openr
    openr = build_opener(CachingRedirectHandler)
    openr.addheaders = [('User-agent', 'Mozilla/5.0')]
    return openr

opener = _create_opener()


def urlopen(url):
    """
    Opens a url specified by the ``url`` parameter.

    This function handles redirect caching, if enabled.
    """
    # warnings.warn("urlopen() is a part of the urllib2 based www "
    #               "implementation and is deprecated.", DeprecationWarning)
    url = get_actual_url(url)
    try:
        page = opener.open(url)
        try:
            if ENABLE_REDIRECT_CACHING is True and page.status == 301:
                logger.debug('Detected New Permanent Redirect:\n' +
                             url + '\n' + page.url)
                redirect_cache[url] = page.url
        except AttributeError:
            pass
        return page
    except HTTPError as e:
        logger.error("HTTP Error : {0} {1}".format(e.code, url))
        raise
    except URLError as e:
        logger.error("URL Error : {0} {1}".format(e.errno, e.reason))
        raise


class CacheBase(object):
    def __init__(self, cache_dir=WWW_CACHE):
        self.cache_fs = fsopendir(cache_dir)

    def _get_filepath(self, *args, **kwargs):
        raise NotImplementedError

    def _get_fresh_content(self, *args, **kwargs):
        raise NotImplementedError

    @staticmethod
    def _serialize(response):
        return response

    @staticmethod
    def _deserialize(filecontent):
        return filecontent

    def _is_cache_fresh(self, filepath, max_age):
        if self.cache_fs.exists(filepath):
            tn = int(time.time())
            tc = int(time.mktime(
                self.cache_fs.getinfo(filepath)['modified_time'].timetuple())
            )
            if tn - tc < max_age:
                return True
        return False

    def _accessor(self, max_age, getcpath=False, *args, **kwargs):
        filepath = self._get_filepath(*args, **kwargs)
        if self._is_cache_fresh(filepath, max_age):
            logger.debug("Cache HIT")
            if getcpath is False:
                try:
                    filecontent = self.cache_fs.open(filepath, 'rb').read()
                    return self._deserialize(filecontent)
                except UnicodeDecodeError:
                    # TODO This requires the cache_fs to be a local
                    # filesystem. This may not be very nice. A way
                    # to hook codecs upto to pyfilesystems would be better
                    with codecs.open(
                            self.cache_fs.getsyspath(filepath),
                            encoding='utf-8') as f:
                        filecontent = f.read()
                        return self._deserialize(filecontent)
            else:
                return self.cache_fs.getsyspath(filepath)

        logger.debug("Cache MISS")
        data = self._get_fresh_content(*args, **kwargs)
        try:
            sdata = self._serialize(data)
            fd, temppath = tempfile.mkstemp()
            fp = os.fdopen(fd, 'wb')
            fp.write(sdata)
            fp.close()
            logger.debug("Creating new cache entry")
            # This can be pretty expensive if the move is across a real filesystem
            # boundary. We should instead use a temporary file in the cache_fs
            # itself
            movefile(temp_fs, temp_fs.unsyspath(temppath),
                     self.cache_fs, filepath)
        except:
            raise

        if getcpath is False:
            return data
        else:
            return self.cache_fs.getsyspath(filepath)


class WWWCachedFetcher(CacheBase):
    """
    This class implements a simple filesystem cache which can be used
    to create and obtain from cached www requests.

    The cache is stored in the ``cache_fs`` filesystem, with a filename
    constructed from the md5 sum of the url (encoded as ``utf-8`` if
    necessary).

    If the fetcher's ``fetch`` function is called with the ``getcpath``
    attribute set to True, the fetcher will simply return the path
    to a (valid) file in the cache filesystem, and opening and reading
    the file is left to the caller. This hook is provided to help deal
    with file encoding on a somewhat case-by-case basis, until the
    overall encoding problems can be ironed out.
    """
    def _get_filepath(self, url):
        # Use MD5 hash of the URL as the filename
        if six.PY3 or (six.PY2 and isinstance(url, unicode)):
            filepath = md5(url.encode('utf-8')).hexdigest()
        else:
            filepath = md5(url).hexdigest()
        return filepath

    def _get_fresh_content(self, url):
        # Retrieve over HTTP and cache, using rename to avoid collisions
        return urlopen(url).read()

    def fetch(self, url, max_age=500000, getcpath=False):
        # warnings.warn(
        #     "WWWCachedFetcher() is a part of the urllib2 based "
        #     "www implementation and is deprecated.",
        #     DeprecationWarning
        # )
        return self._accessor(max_age, getcpath, url)


#: The module's :class:`WWWCachedFetcher` instance which should be
#: used whenever cached results are desired.
cached_fetcher = WWWCachedFetcher(cache_dir=WWW_CACHE)


def get_soup(url):
    """
    Gets a :mod:`bs4` parsed soup for the ``url`` specified by the parameter.
    The :mod:`lxml` parser is used.
    This function returns a soup constructed of the cached page if one
    exists and is valid, or obtains one and dumps it into the cache if it
    doesn't.
    """
    page = cached_fetcher.fetch(url)
    if page is None:
        return None
    soup = BeautifulSoup(page, 'lxml')
    return soup


def _get_proxy_dict():
    """
    Construct a dict containing the proxy settings in a format compatible
    with the :class:`requests.Session`. This function is used to construct
    the :data:`_proxy_dict`.

    """
    if NETWORK_PROXY_TYPE == 'http':
        proxyurl = _get_http_proxy_url()
        return {'http': proxyurl,
                'https': proxyurl}
    else:
        return None

#: A dict containing the proxy settings in a format compatible
#: with the :class:`requests.Session`.
_proxy_dict = _get_proxy_dict()


def _get_requests_cache_adapter(heuristic):
    """
    Given a heuristic, constructs and returns a
    :class:`cachecontrol.CacheControlAdapter` attached to the instance's
    :class:`cachecontrol.caches.FileCache`.

    """
    return CacheControlAdapter(
        cache=FileCache(REQUESTS_CACHE),
        heuristic=heuristic,
        cache_etags=False
    )


def get_session(target='http://', heuristic=None):
    """
    Gets a pre-configured :mod:`requests` session.

    This function configures the following behavior into the session :

    - Proxy settings are added to the session.
    - It is configured to use the instance's :mod:`CacheControl` cache.
    - Permanent redirect caching is handled by :mod:`CacheControl`.
    - Temporary redirect caching is not supported.

    Each module / class instance which uses this should subsequently
    maintain it's own session with whatever modifications it requires
    within a scope which makes sense for the use case (and probably close
    it when it's done).

    The session returned from here uses the instance's REQUESTS_CACHE with
    a single - though configurable - heuristic. If additional caches or
    heuristics need to be added, it's the caller's problem to set them up.

    .. note::
        The caching here seems to be pretty bad, particularly for digikey
        passive component search. I don't know why.

    :param target: Defaults to ``'http://'``. string containing a prefix
                   for the targets that should be cached. Use this to setup
                   site-specific heuristics.
    :param heuristic: The heuristic to use for the cache adapter.
    :type heuristic: :class:`cachecontrol.heuristics.BaseHeuristic`
    :rtype: :class:`requests.Session`

    """

    s = requests.session()
    if _proxy_dict is not None:
        s.proxies.update(_proxy_dict)
    if heuristic is None:
        heuristic = ExpiresAfter(days=5)
    s.mount(target, _get_requests_cache_adapter(heuristic))
    return s


def get_soup_requests(url, session=None):
    """
    Gets a :mod:`bs4` parsed soup for the ``url`` specified by the parameter.
    The :mod:`lxml` parser is used.

    If a ``session`` (previously created from :func:``get_session``) is
    provided, this session is used left open. If it is not, a new session
    is created for the request and closed before the soup is returned.

    Using a caller-defined session allows usage of a single session across
    multiple requests, therefore taking advantage of HTTP keep-alive to
    speed things up. It also provides a way for the caller to modify the
    cache heuristic, if needed.

    Any exceptions encountered will be raised, and is left for the caller
    to handle. The assumption is that a HTTP or URL error is going to make
    the soup unusable anyway.

    """
    if session is None:
        session = get_session()
        _close_after = True
    else:
        _close_after = False

    r = session.get(url)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, 'lxml', from_encoding=r.encoding)

    if _close_after is True:
        session.close()
    return soup


class ThrottledTransport(HttpAuthenticated):
    def __init__(self, **kwargs):
        self._minumum_spacing = kwargs.pop('minimum_spacing', 0)
        self._last_called = int(time.time())
        HttpTransport.__init__(self, **kwargs)

    def send(self, request):
        now = int(time.time())
        tsincelast = now - self._last_called
        if tsincelast < self._minumum_spacing:
            tleft = self._minumum_spacing - tsincelast
            logger.debug("Throttling for {0}".format(tleft))
            time.sleep(tleft)
        self._last_called = now
        return HttpAuthenticated.send(self, request)


class CachedTransport(CacheBase):
    def __init__(self, **kwargs):
        cache_dir = kwargs.pop('cache_dir')
        self._max_age = kwargs.pop('max_age', 600000)
        CacheBase.__init__(self, cache_dir=cache_dir)

    def _get_filepath(self, request):
        # Use MD5 hash of a combination of the URL and the message
        # as the filename
        keystring = request.url + request.message
        if six.PY3 or (six.PY2 and isinstance(keystring, unicode)):
            filepath = md5(keystring.encode('utf-8')).hexdigest()
        else:
            filepath = md5(keystring).hexdigest()
        return filepath

    def _get_fresh_content(self, request):
        response = HttpAuthenticated.send(self, request)
        return response

    @staticmethod
    def _serialize(response):
        if response.code != 200:
            logger.debug("Bad Status {0}".format(response.code))
            raise ValueError
        return pickle.dumps(response)

    @staticmethod
    def _deserialize(filecontent):
        return pickle.loads(filecontent)

    def send(self, request):
        response = self._accessor(self._max_age, False, request)
        return response


class CachedThrottledTransport(ThrottledTransport, CachedTransport):
    def __init__(self, **kwargs):
        cache_dir = kwargs.pop('cache_dir')
        max_age = kwargs.pop('max_age', 600000)
        CachedTransport.__init__(self, cache_dir=cache_dir, max_age=max_age)
        ThrottledTransport.__init__(self, **kwargs)

    def _get_fresh_content(self, request):
        response = ThrottledTransport.send(self, request)
        return response

    def send(self, request):
        return CachedTransport.send(self, request)


def get_soap_client(wsdl, cache_requests=True,
                    max_age=600000, minimum_spacing=0):
    if cache_requests is True:
        soap_transport = CachedThrottledTransport(
            cache_dir=SOAP_CACHE, max_age=max_age,
            minimum_spacing=minimum_spacing,
            proxy=_proxy_dict,
        )
    else:
        soap_transport = HttpAuthenticated()
    return Client(wsdl, transport=soap_transport)
