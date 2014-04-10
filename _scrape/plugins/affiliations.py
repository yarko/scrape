#
#
# Scrape  affiliations plugin;

import csv
import re
import string
from StringIO import StringIO
from functools import partial


'''
Affiliations -

Given a list of authors, and a list of affiliations, parse them out in
preparation for csv output.

The functions here starting with '_' are private to this plugin, and should not
be called from Scrape

'''

# Required:
# a global for this plugin namespace:
logger = None
def register(host_logger):
    '''
    mandatory registration function;
    '''
    global logger
    logger = host_logger
    
#---< end of register() >---#

#  \xe2\x80\x94 => effectively an em-dash;

# JAMA needed:
_honorific = ('Drs ', 'Dr ', 'Ms ', 'Mrs ', 'Mr ')
discard_honorific = lambda a:  a.split(None,1)[-1] if a.startswith(_honorific) else a

# dicard d from the leading edge of a:
discard_leading = lambda d, a: a[a.find(d)+len(d):] if a.strip().startswith(d) else a
_complex_affiliation = lambda s: len(re.findall('[)]', s))>1

# to split a name list, such as "A, B, and C" or "A and B":
namelist = re.compile(r'(?:,\s(?:and\s)?|\sand\s)')

# TODO:
#  - this is now perilously close to clean_jco_author();
#  - see notes there...
#  - use partials to set options for use from map()
def clean_author(item, filter_honorifics=True, word='and', wordsplit=True):
    i = item.strip(string.whitespace+string.punctuation)
    # we only do one or the other of these
    if wordsplit and i.find(' '+word+' ')>0:
        i= i.split(' '+word+' ')  # returns a list
    elif i.startswith(word+' '):
        i = i.split(word+' ')[1:]  # this returns a list
    else:  # ensure we uniformly return a list;
        i = [i]
    # need to handle things like: "Dr Foo and Ms Bar"
    if filter_honorifics:
        return [discard_honorific(a) for a in i]
    else:
        return i 

# need to split affiliations into something similar to jama - complex affiliations

### 
# we're going to head down this similarly as for jama affiliations - complex & simple;
#  then see if we can parameterize based on common structure.

def parse_affiliations(affiliations, process_author=lambda a:[a], parse_institution=None):
    '''
    parse_affiliations:   parses complex affiliation lists (of any form);
    RETURNS:
       dictionary of authors: [list of affiliated institutions]
       
       If authors are input as last-name, or initials, that is what is output;
       
    PARAMETERS:
    
        affiliations:  a list of affiliation strings from the source;
            assumed form:   dept/divn + institution (list of authors)
            or              dept/divn (authors), another dept/divn (authors), ... institution;
            or              the above, repeated for multiple institution names for one location (city);
            
        process_author:  a function to process (filter / clean) indivitual author entries;
            should return:  expected to return a list
            default:   identity (author returned in form of a list);
        parse_institution:  a function which will split a string in two,
                 leaving L[0] with institution name,  L[1] with the next dept/divn name;
            default:   None
         
    '''
    result = {}
    deferred = []
    # if we're splitting before this 
    for row in affiliations:

        if _complex_affiliation(row):
            # each affiliation set has the form:
            # - If complex (multi-department, same institution):
            #   - If first entry, then leading "From the Departments of..."
            #   - department name;
            #   - parenthesized list of author initials (W.H, H.G.)
            #   - a tail part of the institution
            # - else:
            #   - the dept & institution
            #   - parenthesized list of author initials;
            
            # This seems to be special handling for NEJM:
            # get rid of any pesky em-dashes:
            row = row.replace(' \xe2\x80\x94', ',')
            af = [j.split(' (') for j in row.split('), ')]
            locn = ''
            if af[-1][0].startswith('all in '):
                locn = ', '+af[-1][0][len('all in '):]
                af.pop()
            #  this won't be same as jama_affiliations, because of the structure:
            # af:
            # - 2 item list:  [dept., authors]
            #   - grab dept.;
            #   - split list of authors
            # - if last item is len==1, then it's the institution;
            inst = ""
            for n in af:
                # assert len(n)>1, "affiliation record is too short; expected a list!: {}".format(n)
                # if there's an institution, emit, else continue to process
                if len(n)==1:
                    inst = n[0]
                    while deferred:
                        auth, dept = deferred.pop()
                        result[auth].append("{}, {}{}".format(dept, inst, locn))
                    continue
                elif parse_institution:
                    x = parse_institution(n[0])
                    if len(x)>1:
                        # then expected:
                        #  - [institution, next dept (followed by next institution)]
                        inst = x[0]
                        n[0] = x[1]
                        while deferred:
                            auth, dept = deferred.pop()
                            result[auth].append("{}, {}{}".format(dept, inst, locn))
                    # else just fall thru

                dept = discard_leading('the ', discard_leading('and ', n[0])).replace('Departments', 'Department')
                authors = []
                if len(n)>1:
                    for item in map(process_author, namelist.split(n[-1])):
                        # ensure each item is a list item
                        if not isinstance(item, list):
                            logger.error("author processing routing must return a list; {} didn't.".format(process_author))
                        authors.extend(item)
                for a in authors:
                    # DEBUG:
                    # if a.startswith('Dr') or a.startswith('Ms'):
                    #    pass
                    if not result.has_key(a):
                        result[a] = []  # all results are lists
                    #result[a].append("{}, {}".format(dept, inst))
                    deferred.append([a, dept])
        # single affiliate, one+ authors
        elif row[-1] == ')':  # the most usual case
            af = row[:-1].split(' (')
            # now - affiliation == af[0], authors == af[1];
            # parse the authors
            authors = []
            # This is a bug:  we need to do process_author here too,
            #  otherwise we have duplicitous processing in these two cases:
            # NO: enlist = lambda a: [a]
            # NO: for item in map(enlist, namelist.split(af[-1])):
            for item in map(process_author, namelist.split(af[-1])):
                authors.extend(item)  # each item is a list
            affiliate = discard_leading('the ', discard_leading('and ',af[0].strip(string.whitespace+string.punctuation)))
            for a in authors:
                # DEBUG:
                # if a.startswith('Dr') or a.startswith('Ms'):
                #    pass
                if not result.has_key(a):
                    result[a] = []  # make all result items lists
                result[a].append(affiliate)
        else:
            # TODO:  change this to a logger.error message
            if not row[-1] == ')':
                logger.error("unexpected string for affiliation:\n{}".format(i))

    return result


############## ---<  NEJM >--- #####################
##
# authors are listed in comma-pairs:  (name, title)
# the affiliate organization is implicit...
# the affiliations are a comma separated list of strings, consisting of:
# - dept. (followed by comma-separated list of author initials)
# - will need to parse names to initial sets

## afresults = parse_affiliations(affiliations)
# TODO:
# - now parse author initials into authors, for NEJM

def _get_hyphinitial(s):
    if s.endswith('.'):  # e.g. "M.K."
        y = [i[0] for i in s[:-1].split('.')]
    else:
        y = [i[0] for i in s.split('-')]
        for i, v in enumerate(y[1:], 1):
            y[i] = '-'+v
    return y
    

def _nejm_affiliations(authors, aff):
    res = parse_affiliations(aff, parse_institution=lambda s: s.split(', the ') )
    # TODO:
    # - need to replace "if s in a" with the split / first letters of each item
    # TODO:
    # - this is a start; need to handle hypenated names, which initial as:
    #   Rab-Bar =>  R.-B.
    get_initials = lambda x: '.'.join([i for j in x.split() for i in _get_hyphinitial(j)])+'.'
    # probably better here to just generate the initial to author list:
    auth_by_initials = {}
    for i,a in enumerate(authors):
        auth_by_initials[get_initials(a)] = (i, a)
    author_fullname = lambda s: auth_by_initials[s][1]
    author_index = lambda s: auth_by_initials[s][0]
    initials = ['']*len(authors)
    # affiliations are lists;
    affiliations = [[]]*len(authors)
    for k in res.keys():  # author initials
        i = author_index(k) # a list
        # leave this as author initials
        initials[i] = k
        affiliations[i] = res[k]
    return initials, affiliations


def nejm(authors, affiliations):
    '''
    Main entry point for NEJM Affiliations parsing;
    both parameters are lists (affiliations is expected to contain a single
    string)
    '''
    # NEJM authors have degrees, potentially more than one per author
    # author_list = svars['authors'][0].split(', ')
    # TODO: will namelist work properly here?:
    #author_list = authors[0].split(', ')
    author_list = namelist.split(authors[0])
    # TODO: will we need the following discard_leading line now???
    authors = [discard_leading('and ', i) for i in author_list if i[-1] != '.']

    # affiliations = svars["affiliations"][0].strip(string.whitespace+string.punctuation).split('; ')
    affiliations = affiliations[0].strip(string.whitespace+string.punctuation).split('; ')
    affiliations[0]  = discard_leading('From ', affiliations[0])
    affiliations[-1] = discard_leading('and ',  affiliations[-1])
    # now 
    # initials, affiliations = nejm_affiliations(authors, affiliations)
    return _nejm_affiliations(authors, affiliations)
    # svars['author_by_initials'] = initials
    # svars['author_affiliations'] = affiliations

##
############## ---< END of NEJM >--- #####################


############## ---<  JAMA  >--- #####################
##

def _jama_affiliations(authors, aff):
    # OLD:
    # res = parse_affiliations(aff)
    # NEW:
    res = parse_affiliations(aff, process_author=clean_author)
    author_fullname = lambda s: [(i,a) for i,a in enumerate(authors) if s in a]
    author_index = lambda s: [i for i,a in enumerate(authors) if s in a]
    lastnames = ['']*len(authors)
    # affiliations are lists;
    affiliations = [[]]*len(authors)
    for k in res.keys():  # author last names
        i = author_index(k) # a list
        if not len(i) == 1:
            logger.error( "match for author [{}] failed: ({} found).".format(k, len(i)) )
            continue
        i = i[0]
        # leave this as author lastname,
        lastnames[i] = k
        affiliations[i] = res[k]
    return lastnames, affiliations


def jama(authors, affiliations):
    ''' returns lastnames, affiliations '''
    # s = svars['affiliations'][0][0]
    s = affiliations[0][0]
    aff= s.split(': ',1)[-1][:-1].split('; ')
    aff[-1] = discard_leading('and ', aff[-1])
    return _jama_affiliations(authors, aff)
    # lastnames, affiliations = _jama_affiliations(authors, aff)
    # svars['author_lastname'] = lastnames
    # TODO:   affiliations still showing starting w/ "and ..."
    # svars['author_affiliations'] = affiliations

##
############## ---< END of JAMA >--- #####################


############## ---<  JCO  >--- #####################
##

_unsplit = re.compile('[,]? ')

def _coalesce_institution(lst, authors, master):
    for n in range(len(lst)-1, -1, -1):  #walk from the back of the list
        if lst[n] in authors:
            break
    n += 1  # first list item not in authors;
    # make it one item;
    # - if the institution was split on comma's, this works:
    # - if on 'and', then we need to go to the source
    proto = ", ".join(lst[n:])
    # given a proto (with potentially missing words) and a master,
    #   return the correct portion of the master which proto starts with
    m = re.search(_unsplit.sub(r'[,]?\s\S*\s*', proto), master)
    inst = m.group() if m else proto
    del(lst[n:])
    lst.append(inst)
    return lst

_clean_jco_author = partial(clean_author, filter_honorifics=False)

def _parse_jco_affiliations(authors, affiliations):
    "JCO affiliations are ';\n' separated, so we use csv reader"

    io = StringIO(affiliations.strip())
    csvread = csv.reader(io)
    result = {}   # author: [list of affiliations]

    for row in csvread:
        # every row is an affiliation list;
        # - author list, ending with
        # - the institution;
        af = []
        #  if the institution has an "and" as part of it's
        #  name, this will loose it:
        for i in map(_clean_jco_author, row):
            af.extend(i)  # a possibly multi-itemed list;

        # institution might have been split (by commas, or 'and's)
        #   into more than one list-item;
        #   - coalesce will fix the potential of losing an 'and' in institution name
        #     by looking at the original form
        af = _coalesce_institution(af, authors, affiliations)

        # authors are all but last list item:
        # institution is the last list item;
        institution = af[-1]

        for authr in af[:-1]:
            if not result.has_key(authr):
                result[authr] = [] # ensure all results are lists
            result[authr].append(institution)

    return result


# could just as easily have this be '..if s == a', but
#  I'd prefer to keep this the same lambda def for many...
author_index = lambda s: [i for i,a in enumerate(authors) if s in a]

def jco(authors, affiliations):
    'return affiliations lists corresponding to the author list positions'

    res = _parse_jco_affiliations(authors, affiliations)
    af = [[]] * len(authors)
    # TODO:  This is messy and potentially unreliable:
    #   converting relations (dicts) to lists.
    #   - Tables lose info, and this is part of a fragile structure;
    #   - consider instead, keeping all in a document db, and
    #   - allowing table extraction as just a part of the process,
    #     on demand.
    for k in res.keys():  # author last names
        i = author_index(k) # a list
        if not len(i) == 1:
            logger.error("match for author [{}] failed (size {} found).".format(k,len(i)))
            continue
        af[i[0]] = res[k]
    
    return af

# now, just need to order them for table output.
#  - probably want this in the form of an author dict;

# ordered_affiliations = jco_affiliations(authors, affiliations)


##
############## ---< END of JCO >--- #####################
