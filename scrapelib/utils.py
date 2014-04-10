##
# utils.py - miscellaneous utils for scrape
#


### lifted from cmd2:
# History stuff:
#
class HistoryItem(str):
    # listformat = '-------------------------[%d]\n%s\n'
    listformat = '[%3d]\t%s\n'
    def __init__(self, instr):
        str.__init__(self)
        self.lowercase = self.lower()
        self.idx = None
    def pr(self):
        return self.listformat % (self.idx, str(self))
        
class History(list):
    '''A list of HistoryItems that knows how to respond to user requests.
    >>> h = History([HistoryItem('first'), HistoryItem('second'), HistoryItem('third'), HistoryItem('fourth')])
    >>> h.span('-2..')
    ['third', 'fourth']
    >>> h.span('2..3')
    ['second', 'third']
    >>> h.span('3')
    ['third']    
    >>> h.span(':')
    ['first', 'second', 'third', 'fourth']
    >>> h.span('2..')
    ['second', 'third', 'fourth']
    >>> h.span('-1')
    ['fourth']    
    >>> h.span('-2..-3')
    ['third', 'second']      
    >>> h.search('o')
    ['second', 'fourth']
    >>> h.search('/IR/')
    ['first', 'third']
    '''
    def zero_based_index(self, onebased):
        result = onebased
        if result > 0:
            result -= 1
        return result
    def to_index(self, raw):
        if raw:
            result = self.zero_based_index(int(raw))
        else:
            result = None
        return result
    def search(self, target):
        target = target.strip()
        if not target:  #short circuit this
            return []
        if target[0] == target[-1] == '/' and len(target) > 1:
            target = target[1:-1]
        else:
            target = re.escape(target)
        pattern = re.compile(target, re.IGNORECASE)
        return [s for s in self if pattern.search(s)]

    spanpattern = re.compile(r'^\s*(?P<start>\-?\d+)?\s*(?P<separator>:|(\.{2,}))?\s*(?P<end>\-?\d+)?\s*$')
    def span(self, raw):
        if not isinstance(raw, str):
            raise IndexError
        if self == [] or self == [''] :  # short circuit this boundary
            return self
        if raw.lower() in ('*', '-', 'all'):
            raw = ':'
        results = self.spanpattern.search(raw)
        if not results:
            raise IndexError
        if not results.group('separator'):
            return [self[self.to_index(results.group('start'))]]
        start = self.to_index(results.group('start'))
        end = self.to_index(results.group('end'))
        reverse = False
        if end is not None:
            if end < start:
                (start, end) = (end, start)
                reverse = True
            end += 1
        result = self[start:end]
        if reverse:
            result.reverse()
        return result
                
    rangePattern = re.compile(r'^\s*(?P<start>[\d]+)?\s*\-\s*(?P<end>[\d]+)?\s*$')
    def append(self, new):
        new = HistoryItem(new)
        list.append(self, new)
        new.idx = len(self)
    def extend(self, new):
        for n in new:
            self.append(n)
        
    def get(self, getme=None, fromEnd=False):
        if not getme:
            return self
        try:
            getme = int(getme)
            if getme < 0:
                return self[:(-1 * getme)]
            else:
                return [self[getme-1]]
        except IndexError:
            return []
        except ValueError:
            rangeResult = self.rangePattern.search(getme)
            if rangeResult:
                start = rangeResult.group('start') or None
                end = rangeResult.group('start') or None
                if start:
                    start = int(start) - 1
                if end:
                    end = int(end)
                return self[start:end]
                
            getme = getme.strip()

            if getme.startswith(r'/') and getme.endswith(r'/'):
                finder = re.compile(getme[1:-1], re.DOTALL | re.MULTILINE | re.IGNORECASE)
                def isin(hi):
                    return finder.search(hi)
            else:
                def isin(hi):
                    return (getme.lower() in hi.lowercase)
            return [itm for itm in self if isin(itm)]

## {{{ http://code.activestate.com/recipes/499305/ (r3)
# import os
import fnmatch

def locate(pattern, root=os.curdir):
    '''Locate all files matching supplied filename pattern in and below
    supplied root directory.'''
    for path, dirs, files in os.walk(os.path.abspath(root)):
        for filename in fnmatch.filter(files, pattern):
            yield os.path.join(path, filename)
## end of http://code.activestate.com/recipes/499305/ }}}

## NOTE:
#   chromedriver_mac_23.0.1240.0   fails to open jama article URLs;
#   Going forward, only supporting Firefox driver...
# !!use_browser = "Chrome"  # or "Firefox"
# use_browser = "Chrome"  # or "Firefox"
use_browser = "Firefox"
# open browser control channels:
# - once open, will return same browswer window channel
# - only two channels opened per session.
class Driver(object):
    _browser = None
    _viewer = None
    # This is so selenium can pull the user's default
    #  Firefox profile for this set of sessions:
    _ff_profile = None  # a webdriver profile
    _use_user_profile = True  # by default, try to use one
    # Don't have to worry about profiles w/ Chrome:
    _chrome_profile = None
    
    def getbrowser(self):
        if not Driver._browser:
            Driver._browser = webdriver.Chrome() if use_browser == "Chrome" \
                else webdriver.Firefox(Driver._getprofile(self))
        return Driver._browser
    def getviewer(self):
        if not Driver._viewer:
            Driver._viewer = webdriver.Chrome() if use_browser == "Chrome" \
                else webdriver.Firefox(Driver._getprofile(self))
        return Driver._viewer
    
    def _getprofile(self):
        # get user's default FF profile if possible
        if Driver._use_user_profile and not Driver._ff_profile:
            import platform

            system = platform.system()
            ff_env = ''
            # from http://support.mozilla.org/en-US/kb/profiles-where-firefox-stores-user-data
            if system.startswith('Darwin'):
                ff_env = os.environ['HOME'] + '/Library/Application Support/Firefox/'
            elif system.startswith('Win'):
                ff_env = os.environ['APPDATA'] +  '/Mozilla/Firefox/'
            elif system.startswith('Linux'):
                ff_env = os.environ['HOME'] + '/.mozilla/firefox/'
            
            # locate the firefox profile
            if not ff_env:
                logger.warn(MSG_NO_PROFILE)
            else:
                for prof in locate('profiles.ini', root=ff_env):
                    import ConfigParser
                    
                    MSG_NO_PROFILE= "Can't find your Firefox profiles configuration."
                    config = ConfigParser.ConfigParser()
                    config.read(prof)
                    pth = None
                    for i in config.sections():
                        if config.has_option(i, 'name') \
                           and config.get(i, 'name').lower() == 'default' \
                           and config.has_option(i, 'path'):
                            pth = config.get(i, 'path')
                            if config.has_option(i, 'isrelative'):
                                rltv = config.get(i, 'isrelative').startswith(('1','y','Y'))
                            profile_path = ff_env + pth if rltv else pth
                            Driver._ff_profile = webdriver.FirefoxProfile(profile_path)
                            break
                    if not pth:
                        logger.warn(MSG_NO_PROFILE)
                        # if this is the case prevent us from thrashing about in the future:
                        Driver._use_user_profile = False
                    
        # no worries: if still "None", selenium will use default profile
        return Driver._ff_profile
    
    browser = property(fget=getbrowser)
    viewer = property(fget=getviewer)

#  Allow css selectors or xpath expressions anywhere, exchangeably:
def csssel_or_xpath(arg):
    pass



# open_tree:  given a filename, return a tree.root
    ##  Note:  html.parse()  - provides all detail;
    #   etree.HTML()  provides minimal _only_ html
    #
    #   html.parse()  does the whole document.

    #  The etree equiv. to html.parse():
    #  parser = html.html_parser
    #  tree = etree.parse(jco, parser)
    #
    #  use doc.body to get at the body of our page:
## open_tree = lambda fn: html.parse(fn).getroot()

URL_HEAD = ('http://','https://','file:///')

def open_tree(fn):
    # if fn is a file path, try to read it with html.parse(),
    #  but we'll have missing functionality;
    # if fn is a url, or starts with "file:///...", then use
    #  selenium to open, unless --batch mode.
    
    isfile = os.path.isfile(fn)
    if BATCH or (isfile and not fn.endswith('.html')):
        return html.parse(fn).getroot()
    
    if isfile:  # convert it to a URI
        nfn = 'file:///' + os.path.abspath(fn)
        fn = nfn
        
    if not fn.startswith(URL_HEAD):
        if not fn:
            msg = "No URI path provided; opening browser; use the 'open' command to process a page you later navigate to."
        else:
            msg = "Not a valid URI path: {}".format(fn)
        logger.warn(msg)
        Driver().browser
        return None
    
    # open the browser; parse the source
    browser = Driver().browser
    browser.get(fn)  # load URI into browser
    node = html.fromstring(browser.page_source)
    return node
    
# TODO:
#  - have a look at how cmd code (parse) handles this,
#   - or try map
#
# Ensure valid python names for internal use;
# returns a dict of names:
#   { valid_python : STATA_output }
def valid_names(name_list):
    name_dict = {}
    # for now:
    good_name = lambda s: s
    for i in name_list:
        # dict: python_name: stata_name
        name_dict[good_name(i)] = i
    return name_dict


def must_open(f, c='r'):
    try:
        fp = open(f, c)
    except IOError as e:
        # e includes the filename in it's message:
        logger.error('Unable to open: %s\n' % (e))
        # exit(2)
        raise
    return fp


def roll_open(f, c='w'):
    n = 0
    nf = f
    sf = os.path.splitext(f)
    while os.path.exists(nf):
        n += 1
        if n > 99:
            logger.error('Unable to open %s for %s - too many files by that name!" % (f, c)')
            # exit(2)
            raise IOError
        nf = sf[0] + "(%d)" % n + sf[1]
    return must_open(f, c)


