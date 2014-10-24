#!/usr/bin/env python

##
from __future__ import print_function
from __future__ import unicode_literals

# scrape.py

__version__ = '0.1a4'


import os   # for getting at user env vars
import sys  # for output to stdout
import types  # for builtin types

import argparse
import re
import string   # for constants

# for output:
import time
import csv
import yaml
import json

import glob

import logging

# for shell processing:
# using envoy in place of 'import subprocess'
# - import from this project, as we've fixed a thing or two
import envoy   # Kenneth Reitz's little wrapper for subprocesses

# parsing
from lxml import etree
from lxml import html

from collections import Iterable
from collections import deque

# browser automation / interface:

from urllib2 import build_opener  # for headless operation

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait # available since 2.4.0
## uncomment when I need this:
# from selenium.webdriver.support import expected_conditions as EC

# command processing

# from cmd import Cmd
# NOTE:  cmd2 is simply not an option:
#  - it changes all sorts of classes, etc.
#    so, for example, scraping parse scripts
#    begin to fail, and "show" command which
#    passes dicts through yaml - yaml code then fails.
#  Just say "no!" to cmd2.

import cmd
### the following, for command completion:
import readline
import rlcompleter

if readline.__doc__.find('libedit') >= 0:
    readline.parse_and_bind("bind ^I rl_complete")
else:  # not sure if we need this; put for symmetry
    readline.parse_and_bind("tab: complete")

### - end - command completion


# and now for our local stuff:
from scrapelib import plugins


## ---< for development use >---
# pylint: disable= pointless-string-statement
'''
# sample data files:

## JCO:
jco_dir = 'jco-samples/'
jco_filename =
'Survival of Older Patients With Cancer in the Veterans Health Administration Versus Fee-for-Service Medicare.html'
jco = jco_dir + jco_filename
# for testing:
#jco = "jco.body.txt"

##  NEJM:
nejm_dir =
'nejm-samples/Neoadjuvant Chemotherapy and Bevacizumab for HER2-Negative Breast Cancer_files/'
nejm_filename = 'NEJMoa1111065.html'
nejm = nejm_dir + nejm_filename

jama = 'http://jama.jamanetwork.com/article.aspx?articleid=1104871'
'''
## ---< [end development use section ] >---

### constants
#
SEPARATOR = '\n'
BATCH = False
# defined for code readability:
CONTAINS = lambda t, s: s.find(t) >= 0
# filter output so as to skip blank lines:
no_blanks = lambda s: '\n'.join([line for line in s.splitlines() if line.strip()])


"""
########
# This is a relic from a previous version;  I used it here to
#   organize the DISPATCHERS and PROCESSORS, so I leave it here
#   as a kind of documentation:
#
# TODO: Could use this to generate calls thru a factory some day,
#       ... just not now:
######
# accepted actions and 'gets':
getnode_calls = frozenset(
    [
     'find',
     'getnext',
     'getparent',
     'getprevious',
     'get_element_by_id',  # TODO: can this be repl. by cssselect?
    ])
# these return list of nodes:
getnodes_calls = frozenset(
    [
     'cssselect',    # like an extended xpath...
     'findall',      # returns array
     'find_class',   # returns array  # TODO: can this be repl. by cssselect?
     'getchildren',  # returns array
    ])
gettext_calls = frozenset(
    ['findtext',
     'text_content',
    ])
attr_getr = frozenset(
    ['attrib',
    ])
text_getr = frozenset(
    ['tail',
     'text',
    ])
"""

# pylint: enable= pointless-string-statement


## Javascript functions:
#  Grab the selection from the browser;
#  - return the error message, and "null" if no selection.
#
JS_GET_SELECTION = '''
var oB = null;
var e = "";    // error msg;
var s = "";    // selection string;
var h = null;  // html context;
var p = null;  // parent's html context;
try{
  oB = document.getSelection();
  if ( oB.rangeCount == 0 ){
     e = "...Select something from the web-page before trying to \'grab\' it."
  }
  else if( oB.rangeCount > 1 ){
     e = "...Warning: multi-selections detected; only the first returned."
  }
  obr = oB.getRangeAt(0);
  s += obr.toString();
  h = obr.startContainer.parentElement.outerHTML;
  p = obr.startContainer.parentElement.parentElement.outerHTML;
}
catch(e) {
  e = "...An error has occurred: "+e.message
}
finally {
 return [e, s, h, p]
}'''


## Logging configuration:

## pylint thinks these configurations are "constants"
#    rather than just like class initialization calls;
#
# pylint: disable= invalid-name
logger = logging.getLogger('scrape.py')
logger.setLevel(logging.WARN)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# console formatting:
cformatter = logging.Formatter('scrape: %(levelname)s - %(message)s')
# history file formatting:
hformatter = logging.Formatter('%(message)s')

# TODO:  config log file name / place:
# File logging handler:
fh = logging.FileHandler('scrape.log.txt')   # file logging
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
# History logging handler:
hh = logging.FileHandler('scrape.script.txt') # history logging
hh.setLevel(logging.INFO)
hh.setFormatter(hformatter)
# TODO   add option to log; may want 3rd handler:
# for now, we won't out to these:
if 0 == 1:   # eventually, we'll configure this somehow
    logger.addHandler(fh)
    logger.addHandler(hh)

# console logging handler
ch = logging.StreamHandler()
ch.setLevel(logging.WARN)
ch.setFormatter(cformatter)
logger.addHandler(ch)

#
# pylint: enable= invalid-name

# Plugins:
#   Python modules w/ register() initializer functions,
#   in _scrape/plugins under (respectively):
#   - local (cwd), or
#   - user ($HOME), or
#   - scrape too installation directory
## plugins.load() returns a dict of {plugin_name: plugin_module}
# delay loading as long as possible;
# In case there are no plugins, only try loading once
uplugin = {}  # pylint: disable= invalid-name
uplugins_loaded = False  # pylint: disable= invalid-name
# This would set globals to the plugin_name, but risk of clash:
####
##  for k,v in imported_plugins:
##       exec( k+"=v" )
##
#  After loading, the modules will be called:
# - sys.modules[modname].function_name(),
#  or more concisely:
#    uplugin[plugin_name].func()


# for string parameter length control:
# TODO:  make an option for setting this; maybe bring into the MainCmd() class;
LIMIT = 12

# pylint: disable= invalid-name
# showtruncated(string), or showtruncated(string, mylimit)
showtruncated = lambda s, l=LIMIT: s[:l] + "..." if len(s) > l else s

# lxml commands which take no arg:
noargcall = ['getnext', 'getprevious', 'getparent', 'getchildren']
# pylint: enable= invalid-name

### main():
#  The main command processor.
#   after parsing command line options, this may (or may not) invoke
#   the interactive command processor.
def main():
    '''
    scrape
    '''
    class MyArgParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: {}\n'.format(message))
            self.print_help()
            sys.exit(2)

    #  argparse generates usage and help; no longer needed here
    description = '''
    Normally, a script file is run over each file_or_url provided.
    Output is one file per table.  Default output format is csv.
    '''

    parser = MyArgParser(description=description)
    parser.add_argument('-s', '--script', #  DELAY SETTING DEFAULT:  default="script.scrape",
           help="the command file used to process input files or URLs")
    parser.add_argument('-i', '--interactive', default=False, action='store_true',
           help="enter interactive mode after processing input files;")
    parser.add_argument('-c', '--console-out', default=False, action='store_true',
           help="send output to the console (stdout) only; by default, output goes to files named by table-names.")
    parser.add_argument('--populous', default=False, action='store_true',
           help="populate short table columns by their last value; default is to leave the cells empty.")
    parser.add_argument('--sparse', dest='populous', default=False, action='store_false',
           help="populate short table columns with empty cells (default). See also: --populous")
    parser.add_argument('-f', '--input-files', nargs='?',
           help="a file containing input files or URLs, one per line; processed before any command line files")
    parser.add_argument('-o', '--output-file',
           help="combine all table outputs into one file")
    parser.add_argument('-O', '--overwrite', default=False, action='store_true',
           help="by default, written output and scripts roll numerically unique names;"  \
              + "this sets write mode to overwrite existing files.")
    parser.add_argument('-k', '--keep-browser',
           help="keep browser open after exit")
    parser.add_argument('-H', '--HEADLESS', default=False, action='store_true',
           help="operate without a browser, try to parse source directly.")
    parser.add_argument('file_or_URL', metavar='FILE', nargs='*',
           help="input file-or-URL to process.")
    parser.add_argument('--maxcellsize', default=512,
           help="warn if output cells are greater than maxcellsize (output not truncated, only warning issued)")
    parser.add_argument('--no-shell-glob', default=False, action='store_true',
           help="when running shell commands, file expansion (globbing) is in effect; this turns it off.")

    args = parser.parse_args()
    scrape = MainCmd()

    scrape.populous = args.populous

    scrape.console_out = args.console_out
    scrape.single_output = args.output_file
    scrape.headless = args.HEADLESS
    scrape.maxcellsize = args.maxcellsize
    scrape.overwrite = args.overwrite
    scrape.sh_glob = not args.no_shell_glob


    if not args.keep_browser:
        import atexit
        atexit.register(Driver().close)

    # Now, respond per command-line arguments

    def ensure(script, input_files):
        '''
        Ensure a default script...
          - NOTE: the default for interactive mode is 'script.scrape'
          -   it will also be used in the case of single command line argument
              as it's indistinguishable from interactive mode.
        '''
        if not script:
            logger.error(
                "Cannot process input_files ({});".format(input_files) + \
                "you must specify a script file."
            )
            exit -1  # pylint: disable= pointless-statement

        global BATCH, uplugin, uplugins_loaded  # pylint: disable=global-statement,invalid-name

        BATCH = True
        if not uplugins_loaded:
            uplugin = plugins.load(logger)
            uplugins_loaded = True

    # first, process external sources from a file-list:
    if args.input_files:
        ensure(args.script, args.input_files)
        with open(args.input_files, "r") as f:  # pylint: disable=invalid-name
            for line in f:
                scrape.onecmd('open '+ line)
                scrape.onecmd('load ' + args.script)
                # TODO:  this would be a good place to put a timer
                # - a decorator would be nice...
                # - there's also a nice example of doing this with "with"

    # next, address any sources listed on the command line:
    if args.file_or_URL:
        # IF more than one command line arg,
        #  or there is a script provided
        # THEN
        #   process in batch mode
        if (not args.interactive and args.script) or len(args.file_or_URL) > 1:
            ensure(args.script, args.file_or_URL)
        for f in args.file_or_URL:   # pylint: disable=invalid-name
            scrape.onecmd('open '+ f)
            if BATCH:
                scrape.onecmd('load '+ args.script)

    # now, there are two more possibilities:
    #  - if we processed in batch, and also
    #    had the interactive flag, then end in interactive:

    # -- how we do this:
    #  - if there is a file, open it;  (that's already happened above)
    #  - next, if there is a script file at this point (continuing developing a script), open it;
    #  - next, run the command loop.

    if (not BATCH) or args.interactive:  # either default cmdloop, or cmd line specd;
        if args.script:  # continue interactive development
            scrape.onecmd('load '+ args.script)
        scrape.cmdloop()


###
# If we were expecting to have more than one invocation of this class (we're not?)
#   we would probably want to put all these class variables in an __init__()
#
class MainCmd(cmd.Cmd):
    'I originally jokingly called this thin layer [s]crepe ;-)'

    intro = '''[S]crape html to [yaml, json or csv] through a thin layer over
    libxml , python, and shell. Type ^D to exit. --(version {})--'''.format(__version__)

    # Cmd setup vars:
    prompt = '[S]crape >>> '
    use_rawinput = True   # we go raw in interactive mode;
    stderr = sys.stderr   # for info msgs we don't want throttled by logger;
    # when populating table, by default fill with '';
    # - if populous==True, then by last value from a column
    populous = False

    nonblank = True   # skip blank lines on output

    # Now:  set (including default) w/ command line options:
    # maxcellsize = 512  # a resonable default; warn is an output cell is larger

    # things you want to expose to the user:
    showable = ('svars', 'slocals', 'sglobals',
                'populous', 'maxcellsize',
                'var_name', 'table_name', 'tables',
                'script', 'headless', 'overwrite',
                'sh_hist', 'sh_glob', 'doc', 'completekey',
                'cmd_trace', 'path',
                 # later, will want to add:
                 # 'single_output', 'console_output',
                 )


    # scrape setup:

    # e.g. matches "[ newtable ]" or "[newtable]"
    is_tablename = re.compile(r'\[[ ]*(?P<n>[^ ]*)[ ]*\]')
    # e.g. matches "< newvar >" or "<newvar>"
    is_scrapevar = re.compile(r'<[ ]*(?P<n>[^ ]*)[ ]*>')
    is_comment = re.compile(r'(^\s*#|\s{2,}#)')
    # e.g. matches "$(some_shell_command  with_options and_args")
    shell_call = re.compile(r'\$\(([^)]+)\)')
    # for "set" command: check for valid left-side var names:
    is_validname = re.compile(r'^[_a-zA-Z][_a-zA-Z0-9, ]*$')
    # for "set" command: parse for generating plugin calls:
    # returns 3 match groups:
    #  - plugin name
    #  - function call in the plugin
    #  - parameter(s) to the call
    plugin_call = re.compile(r"([_a-zA-Z][_a-zA-Z0-9]*)[.]([_a-zA-Z][_a-zA-Z0-9]*)\((.*)\)")

    # for BATCH processing, there is no history:
    history_append = lambda self, s: None if BATCH else self.history.append(s)

    name_overwrite = lambda self, s: s if self.overwrite else roll_name(s)

    # TODO:  (plugins):
    #  To accomodate plugin operations, need to break these out of this structure:
    # scrape vars:
    # and - interestingly enough - these correspond to the lxml "plugin" we should have by default.
    root = None  # the xml parse tree: use root.docinfo.encoding
    doc = None   # the html tree
    node = None

    # preserve_node = False   # reset to doc on new scrape var - unless someone forgot to set one
    preserve_node = True   # let user explicitly reset to doc; don't do it on new scrape var;
    #--< end TODO >---

    var_name = None   # current name in play
    # These are the dicts which contain the vars
    #   - naming to avoid conflict svars => scrape vars
    svars = {}
    slocals = {}   # persist per URI/file
    sglobals = {}   # per per session
    _sv = {}   # the reverse lookup: var:scope-table

    # default to the currently active var:
    ## NOTYET:
    # current_var = lambda slf: slf.svars[slf.var_name]

    # search:
    _search_anchor = 0

    # each table name holds it's output
    # - when a new table is encountered, push current output to
    #   current table, then create new output queue;
    # - when a table close, or end of input is triggered,
    #   then output that table, or all tables in the queue
    # now: svars <= out = {}  # current output;
    tables = deque()  # tuples: (table_name, output_list);
    cmd_trace = deque()   # command stack
    sh_hist = deque()   # shell output stack

    table_name = None   #  going to try this as "None": ''
    # table ordered keys:
    # - so that we keep the order of getting values
    #   and keep the same order in column output
    table_ordered_keys = []
    default_table_name = 'scrape_table'

    # script is the name of the last loaded script
    script = None
    script_default = 'script.scrape'

    # pylint: disable=unused-argument
    def complete_file(self, text, line, begidx, endidx):
        '''
        name this anywhere you want to use glob'd filename completion
        e.g.:  complete_somecommand = complete_file
        '''
        return glob.glob(text+'*')
    # pylint: enable=unused-argument

    ## setup the interactive environent
    def preloop(self):  # add params, as you need...
        # for development:
        # fn = jco
        # fn = jama  # online
        # self.doc = open_tree(fn)
        # self.root = self.doc.getroottree()
        # self.node = self.doc
        # TODO:  get / log history to a user file;
        global BATCH, uplugin, uplugins_loaded  # pylint: disable=global-statement, invalid-name

        BATCH = False
        if not uplugins_loaded:
            uplugin = plugins.load(logger)
            uplugins_loaded = True
        self.history = History()
        ##  I think I prefer to not do this by default:
        # self.onecmd("open")  # open the browser, w/o url in interactive;

        # TODO:
        # process options, command line args;
        #  - doing this inside the class to hold the variables

        # TODO:
        # - process / register plugins
        # - assigning "self.do_<some_function>" should work for registrations;
        # - BUT help doesn't show up.

        # If there is a file to process, do that now, before entering command loop:
        # if option.interactive .... to drop into interactive command mode

    def precmd(self, line):
        # Remove comments ('#') on the line
        m = self.is_comment.search(line)  # pylint: disable=invalid-name
        nline = line[:m.start()] if m is not None  else line

        if len(nline) > 0:
            # <foo> declares an output varialbe / table column to scrape;
            #  Convert it to a command
            if nline[0] == '<':
                nline = self.is_scrapevar.sub(r'var \g<n>', nline)
            # [bar] declares a new output table name
            elif nline[0] == '[':
                nline = self.is_tablename.sub(r'table \g<n>', nline)
            elif nline[0] == '!':
                nline = 'shell ' + nline[1:]
            # embed the output of a shell command anywhere in the command
            # - a string of the form:  $(x)
            #   will be replaced by the output of the shell string, 'x'
            # - a string of the form:  ${n}
            #   will be replaced by the n'th shell output, from the stack
            n = nline.find(r'$(')  # pylint: disable=invalid-name
            if n >= 0:
                runlist = self.shell_call.findall(nline)
                # n:m for list span
                # run the commands l-to-r;
                # replace in line with output r-to-l
                for s in runlist:  # pylint: disable=invalid-name
                    # this puts on the shell output stack
                    self.onecmd('shell ' + s)
                # this will give ns[0] containing head of the line, or ''
                #   and list pairs with 'SHELL_CMD) other_stuff'
                ns = self.shell_call.sub(r'$()', nline).split(r'$()')  # pylint: disable=invalid-name
                for i, c in enumerate(ns):  # pylint: disable=invalid-name
                    if len(c) == 0:  # eliminate empty strings
                        del ns[i]
                outp = []
                while len(ns) > 1:
                    outp.append(ns.pop())
                    outp.append(self.sh_hist.pop().std_out.rstrip('\n'))
                outp.append(ns[0])
                outp.reverse()
                nline = ''.join(outp)

            # TODO: WANT shell redirections / file output redirection;
            # at this point, the <foo> stuff, and all the contents of $(...)
            # are processed.   I want to process
            # ">>> this is my command >  save_output_here.file" so that you can
            # effect what you would normally expect for shell redirection
            # (write and append, i.e. '>' and '>>', and '|' - pipes);   probably will involve
            # something of the form:
            #    self.stdout = logFile = # open(FileName, 'a', 0)
            # and an added postcmd()  to set these back;  for pipes it will be
            # a little different.  Note:  if I'm going to take stdin (?), I
            # will need to deal with the raw-input flag of cmd;


        # TODO: (if desperate):
        # - could add scanner here to ignore file input forms such as
        #   config files have (foo: bar,  or foo= bar)
        # - if really ambitious, could include yaml-like processing, and
        #   handle  nesting based on indents;

        # TODO:  watch this;
        #  after adding future import of unicode_literals,
        #  cmd() was choking on returning this unicode line:
        return str(nline)

    #override: makes no sense here to do the last command:
    def emptyline(self):
        return

    def default(self, line):
        logger.error("Unrecognized command: {}".format(line))
        return

    def report_fn(self, fname):
        "report on the results (size) of a file"
        # don't use logger for this - always report this
        self.stderr.write("wrote {} bytes to {}\n".format(
            os.stat(fname).st_size, fname))

    def write_table(self, name, table, output=None):
        '''
        if output specified, then no output to stdout;
        otherwise output to stdout, and to the table_name.csv, in a rolling fashion;
        '''
        # write out the csv
        keys = list(table.keys())
        key_order = self.table_ordered_keys
        # since we're going to output in the order the table columns were defined,
        #  let's do a basic sanity check:
        if len(keys) != len(key_order):
            logger.error("something is wrong: size of table keys, and their ordered list mismatch!")
            key_order = keys   # abort the ordered list, but at least preserve what we can
        maxlen = max([len(table[i]) for i in keys])

        # Pad out the columns:
        for k in keys:
            repl = table[k][-1] if self.populous else ''
            table[k].extend([repl] * (maxlen - len(table[k])))
        # TODO:  handle errors based on encoding you can't encode (unicode instead of string?)
        # encoding = self.root.docinfo.encoding
        ## SOrry: csv writer only does UTF-8
        encoding = 'utf-8'
        # table_rows = [[table[j][i].encode(encoding=encoding) for j in keys] for i in range(maxlen)]
        # table_rows = [[table[j][i] for j in key_order] for i in range(maxlen)]
        table_rows = [[table[j][i].encode(encoding) for j in key_order] for i in range(maxlen)]
        # Warn about unusually long items, which might cause problems in csv cells
        maxcell = max([len(item) for sublist in table_rows for item in sublist])
        if maxcell > self.maxcellsize:
            logger.warn("max output item size is {};".format(maxcell))

        # TODO: write to stdout for development;
        #  - later, decide how they want table output named;
        if self.single_output:
            output = self.single_output
            mode = "a"
        else:
            mode = "w"
            if isinstance(output, types.NoneType):
                cc = csv.writer(self.stdout)  # pylint: disable=invalid-name
                # output header and body:
                cc.writerow(key_order)
                cc.writerows(table_rows)

            if self.console_out == True:   # only output to console
                return
            # use the table's name for a filename:
            output = name
        ofname = self.name_overwrite(str(output)+'.csv')
        with must_open(ofname, mode) as f:  # pylint: disable=invalid-name
            cw = csv.writer(f)  # pylint: disable=invalid-name
            cw.writerow(key_order)
            cw.writerows(table_rows)
        self.report_fn(ofname)

    # def do_csv(self, line):
        '''csv [file_name]

           write the current table out in CSV form to [table-name].csv
           or file_name (if given).  file_name will overwrite, regardless of 'overwrite' setting.

           Note: this is different than using the 'table' command, as it will pop pending table output,
           as well as do other things.  This is simply taking the current pending output, and saving
           it as CSV, for inspection.
        '''
        # TODO: Not Yet;  write_table is _too_ coupled...

    def do_json(self, line):
        '''usage: json [file_name]

           write the current table out in JSON form to [table-name].json,
           or file_name (if given).  file_name will overwrite, regardless of 'overwrite' setting.
        '''

        # pylint: disable=invalid-name

        # Shame: str(self.table_name) is just a lazy way to
        #   prevent an exception in case there is no table_name
        #    (table_name is None); instead, we just write nothing to "None.json"
        if len(line) > 0:
            fn = line if line.endswith('.json') else line+".json"
        else:
            fn = self.name_overwrite(str(self.table_name)+".json")
        with must_open(fn, 'w') as f:
            json.dump(self.svars, f)
        self.report_fn(fn)
        self.history_append('json '+line)
        # pylint: enable=invalid-name

    def do_yaml(self, line):
        '''usage: yaml [file_name]

           write the current table out in YAML form to [table-name].yml,
           or file_name (if given).  file_name will overwrite, regardless of 'overwrite' setting.
        '''
        # pylint: disable=invalid-name
        if len(line) > 0:
            fn = line if line.endswith('.yml') else line+".yml"
        else:
            fn = self.name_overwrite(str(self.table_name)+".yml")
        with must_open(fn, 'w') as f:
            yaml.dump(self.svars, f, default_flow_style=False)
        self.report_fn(fn)
        self.history_append('yaml '+line)
        # pylint: enable=invalid-name

    def do_grab(self, line):
        '''usage:  grab [n]

           grab the selected browser text.

           if optional argument is provided:

           n: 1 - find xpath for the parent's parent tree;
           n: 2 - find xpath for the parent tree
           n: 3 - (default) find xpath for the selected text only

           Note: for 1, 2:  finding instances extremely unlikely, as
                 order of tags returned from browser will vary;

        '''
        # this is static, so it the channel only gets created once
        browser = Driver().browser
        # returned list: [error, text, context, parent]
        #  - save for later showing, if desired
        # ugh! => encode it all to utf-8:
        self.grab = browser.execute_script(JS_GET_SELECTION)
        if self.nonblank:
            grab = []
            for val in self.grab:
                grab.append(no_blanks(val))
        else:
            grab = self.grab

        # TODO: there is some piece missing here; this doesn't make sense,
        #   - there must be more to this working or not working:
        if not 'unicode_literals' in globals():
            grab = [i.encode('utf-8') for i in grab]

        # TODO:
        if not grab:
            pass  # write some warning

        # pylint: disable=star-args
        self.stdout.write("\t{}\ntext:\n\t{}\n\nhtml:\n\t{}\n\nparent html:\n\t{}\n\n".format(*grab))
        # pylint: enable=star-args

        # pylint: disable=invalid-name

        # now get the
        # - find it;
        n = 3
        if line:
            if line in ('1', '2', '3'):
                n = int(line)
            else:
                logger.error("argument must be either '1', '2', or '3'")
                return
        # pylint: enable=invalid-name

        # Be sure to run this screen selection against the entire doc
        # - save and restore the current node
        stack = deque()
        stack.append(self.node)
        self.node = self.doc
        # search_string = re.escape(grab[-n]))
        # search_string = grab[-n].encode('unicode-escape')
        # self.onecmd("search "+search_string)
        self.onecmd("search "+grab[-n])
        # now restore the previous
        self.node = stack.pop()

    def do_body(self, arg):
        '''body:  sets the document root to the body of the page.

           Normally, navigation through the document is incremental.
           This resets to starting point for navigation to the start of the <body> tag.
           See also:  doc (which resets to the root of the document, including the header).
        '''
        self.node = self.doc.body
        self.history_append('body')

    def do_root(self, arg):
        '''root:  sets the document root to the top of the html page.

           Normally, navigation through the document is incremental.
           This resets to starting point for navigation to the start of the <html> tag.
           See also:  body (which resets to the <body> of the document).
        '''
        self.node = self.doc
        self.history_append('root')

    # doc == root; just an alias
    do_doc = do_root

    def do_getpath(self, arg):
        '''usage:  getpath [n|-n]

        Returns the xpath expression for the current node(s); useful for developing scripts.

         n: limit output to the first n.
        -n: limit output to the last n.
        '''
        # html elements must always be relatively rooted
        # - also, this getpath includes the parent node ('html'), but we search
        # - relative to that, so have to take it off for the path to be useful
        n = 0

        if arg:  # I don't really care if they say "5" or "+5"
            if isinstance(arg, int):
                n = int(arg)
            else:
                logger.warn("getpath: invalid parameter '{}'; ignored;".format(arg))

        nodes = self.node
        if nodes is None:
            self.stdout.write("--None--\n")
            return
        if not isinstance(nodes, list):
            nodes = [nodes]

        if n != 0:   # show just first or last 'n'
            nodes = nodes[:n] if n > 0 else nodes[n:]

        head = '/html'
        for node in nodes:
            path = self.root.getpath(node)
            # strip the '/html/...' off, if there
            #  - since our tree is rooted at html,  xpath '.' == '/html'
            if path.startswith(head):
                path = path[len(head):]
            self.stdout.write('.'+path+'\n')

    # use file-name completion here too
    complete_open = complete_file

    def do_headless(self, arg):
        'headless: sets scrape to attempt to parse targets directly (without a browser)'
        self.headless = True

    def do_notheadless(self, arg):
        'notheadless: sets scrape to to parse targets with a browser'
        self.headless = False

    def do_glob(self, arg):
        'glob: sets glob filename expansion for shell commands from [s]crape (default).'
        self.sh_glob = True

    def do_noglob(self, arg):
        'noglob: set no filename expansion for shell commands from [s]crape.'
        self.sh_glob = False

    def do_overwrite(self, arg):
        '''overwrite: sets table (csv, yaml, json) and script saving to overwrite if a file already exists.

           Note: providing filenames on many of these commands will assume you know what you want,
                i.e. do overwriting.
        '''
        self.overwrite = True
        self.history_append('overwrite')

    def do_roll(self, arg):
        '''roll: sets table (csv, yaml, json) writing, and script saving to rolling filenames;
            - if a file already exists, adds a unique number to its name.

           Note: providing filenames on many of these commands will assume you know what you want,
                i.e. do overwriting regardless of this setting.

        notoverwrite is an alias for roll.
        '''
        self.overwrite = False
        self.history_append('notoverwrite')

    do_notoverwrite = do_roll

    def do_open(self, arg):
        '''usage:  open [FILE-or-URL]

        Open a new input source to scrape.

        When you don't provide a FILE-or-URL:

          If you're using interactive mode and have
          a file opened in the scrape-controlled browser,
          then that browser document will be parsed,
          and the tree loaded into [S]crape.

          If you don't have a scrape-controlled browser open yet,
          this will open one to 'about:blank'.

        scrape is an alias for open.
        '''
        fn = arg
        # if no arg, and headless => open a blank browser window
        if (not arg) and (self.headless is True):
                fn = 'about:blank'
                self.headless = False

        try:
            self.doc = open_tree(fn, self.headless)
        except IOError as e:
            logger.error('{}'.format(e.message))
            if arg:
                logger.error("\'{}\' may require opening through a browser...".format(fn))
            return
        except Exception as e:  # catch all others
            logger.error("Unknown error: {}".format(e.message))
            return

        self.root = None if self.doc is None else self.doc.getroottree()
        self.node = self.doc
        # locals need to be cleared
        self.slocals = {}

    do_scrape = do_open

    def do_close(self, arg):
        "close:  close the current browser connection (sets mode to 'headless')"
        Driver().close()
        self.headless = True

    def do_base(self, arg):
        '''usage:  base [url]
        Show or set the current input's base url;  used for automatically locating scripts [not yet].
        '''
        self.stdout.write(self.doc.base)
        if arg:
            self.history_append('base ' + arg)

    # settings from interactive mode:
    def do_populous(self, line):
        '''populous:
        when writing tables, populate colums out with their last value.
        see also: sparse.
        '''
        self.populous = True
        self.history_append('populous')

    def do_sparse(self, line):
        '''sparse:
        When writing tables, populate colums with '' (opposite of populous).
        see also: populous.
        '''
        self.populous = False
        self.history_append('sparse')

    # TODO:  evaluate how well this works (may need a separate complete routine for this)
    # this may help find local commands,
    #   or local file args

    # use file-name completion here too
    complete_shell = complete_file
    def do_shell(self, arg):
        '''shell:
        execute a shell command.
        see also: glob and noglob.

        '!' is an alias for shell.
        '''
        # os.system(arg)
        # sub_cmd = subprocess.Popen(arg, shell=True, stdout=subprocess.PIPE)
        #  --- too messy:
        #  -- Instead, use my fixed-up version of Kenneth Reitz's envoy
        if not arg:
            logger.warn("shell: no command to run; nothing to do!")
            return
        try:
            r = envoy.run(arg, globbing=self.sh_glob)
            self.sh_hist.append(r)
        except OSError as e:
            logger.error("{}: {}".format(arg.split()[0], e.strerror))
            return
        # if r.status_code != 0:
        #     logger.warn("{}: returned status code {:d}\n\t{}"\
        #                 .format(arg, r.status_code, r.std_err))
        print(r.std_out if r.status_code == 0 else r.std_err)

    def help_complete(self, line):
        complete_help = [
            "Command line completion is available for many commands in interactive use.",
            "\nThere are two ways to actiate this:",
            "\nThe default completion key is the [tab] key.",
            "\t- [tab] will complete as much of the command",
            "\t-       (or filename or, where available, argument) as possible;",
            "\t- [tab][tab] will show a list of possible completions (changes with how much you've typed);",
        ]
        for s in complete_help:
            self.stdout.write(s+'\n')

    def help_current(self, arg):
        help = '''current: an alias for 'show', for example 'current var' or 'current table_name'
        '''
        print(help)

    def help_identchars(self, arg):
        help = '''
            For variables and tables, valid names consist of
            any character - underscore or alphanumeric,
            except the first character may not be numeric.
        '''
        print(help)

    help_validchars = help_identchars

    def help_show(self, line):
        general = "show various values within the current context."
        # TODO:
        #  - grab these from the self vars themselves;
        #  - -describe the selv vars
        show_help = {
            'cmd_trace': "command trace; show cmd_trace[-1] shows the last command;",
            'completekey': "key used for command completion (default: [TAB]); set from command line",
            'doc': "entire html doc under processing (being scraped)",
            'node': "current document node (after commands executed).  Reset to 'doc' on var declaration",
            'script': "the most recent script file which was loaded and executed.",
            'out': "pending output for current table (not necessarily in final form).",
            'sh_hist': "the shell execution history (with output); inline shell commands are not saved here.",
            'table_name': "the current table name.",
            'table': "alias for table_name.",
            'tables': "list of pending tables (when processing is nested).",
            'var': "the current output var being processed.",
            'var_name': "an alias for 'var'",
            'headless': "shows setting; headless means without browser.",
            }
        this_header = "Available items to show (type 'help show <topic>', or 'help show all'):"
        self.stdout.write("show:\n")
        if line:
            topics = line if line[0] in show_help else show_help
            for topic in topics:
                print('show {}:\t{}'.format(topic, show_help[topic]))
        else:
            # general usage
            self.stdout.write(general)
            self.stdout.write("{}\n".format(str(self.doc_leader)))
            ## As long as I'm using future imports unichar_literals,
            #   we have to be careful of string interactions w/ cmd.py:
            # self.print_topics(str(this_header),   list(show_help.keys()),   15,80)
            self.print_topics(str(this_header), [str(i) for i in show_help.keys()], 15, 80)
        # show this unless a single cmd help requested:
        if not len(line) == 1:
            self.print_topics(str("additionally, show these [s]crape settings:"),
              [str(i) for i in self.showable if i not in show_help.keys()], 15, 80)

    '''
    def complete_show(self, text, line, begidx, endidx):
        if not text:
            completions = self.FRIENDS[:]
        else:
            completions = [f
                           for f in self.FRIENDS
                           if f.startswith(text)
                          ]
        return completions
    '''

    def do_show(self, what=''):
        '''show:
        show variables from the current context.
        current and sh are aliases for show.

        '''
        # translation for what we offer user; could put abbrev's here too:
        show_xlat = {
            'glob':'sh_glob',
            'out':'svars',
            'shell':'sh_hist',
            'table':'table_name',
            'var':'var_name',
            'xpath':'path',
        }
        if not what or what == 'node':
            show_whats = self.node
            if show_whats is None or len(show_whats) == 0:
                show_whats = [self.doc]
        elif what == 'help':
            self.stderr.write("...perhaps you meant help?...\n")
            self.onecmd('help')
            return
        else:  # not really useful for users at this point.
            # if hasattr(self, what):
            # TODO:  this is temporary;
            if what in show_xlat:
                what = show_xlat[what]
            try:
                show_whats = eval('self.' + what) if what in self.showable \
                        else eval('self._sv["' + what + '"]["'+what+'"]')
            except:
                logger.error("Invalid syntax:\n\tshow {}".format(what))
                return
            if not isinstance(show_whats, Iterable) or isinstance(show_whats, (dict, str, unicode)):
                show_whats = [show_whats]
        # TODO: check if any useful idiom for passing params..
        if show_whats is None or len(show_whats) == 0:
            print("--Empty--")  # e.g. sh hist;
            return
        if isinstance(show_whats, str):
            print(show_whats)
            return
        for show_what in show_whats:
            if show_what is not None and isinstance(show_what, type(self.doc)):
                if self.nonblank:
                    print(no_blanks(etree.tostring(show_what, pretty_print=True)))
                else:
                    print(etree.tostring(show_what, pretty_print=True))
            elif isinstance(show_what, envoy.core.Response):
                print(show_what)   # I want to show the instance name too;
                print("{}:\nstatus code: {:d};".format(show_what.command, show_what.status_code))
                print("{}stdout:{}\n{}".format('_' * 8, '_' * 8, show_what.std_out))
                print("{}stderr:{}\n{}".format('_' * 8, '_' * 8, show_what.std_err))
                print('=' * 18)
            elif isinstance(show_what, dict):
                print(yaml.dump(show_what, default_flow_style=False))
            else:
                print(show_what)

    do_sh = do_show
    do_current = do_show  # a convenience alias
    help_current = help_show

    # use file-name completion here too
    complete_load = complete_file
    def do_load(self, filename):
        '''usage:  load file
        Load and run commands from file.'''
        self.script = filename
        try:
            with must_open(filename) as f:
                for line in f:
                    line = self.precmd(line)
                    # TODO:  decide if you'd rather let this run self.emptyline(),
                    #       or always skip blank lines in "load", regardless...
                    if line:
                        self.onecmd(line)
        except Exception as e:
            logger.warn("{}".format(e.message))
            pass

    # use file-name completion here too
    complete_save = complete_file
    def do_save(self, arg): #, opts):
        """usage: save [-arg] [filename]

        Saves command history to filename (the last read script, or 'script.scrape' by default).
        If you provide a filename, I assume you know what you mean - overwrite flags have no effect,
        and that filename is written (or overwritten).

        Use with the 'history' command, to preview / select what to save.

        no arg             -> save all
        integer arg        -> save one history item, by index
        a..b, a:b, a:, ..b -> save a list of commands from history, which
                              span from a (or start) to b (or end)
        string arg         -> save all commands matching string search
        /arg in slashes/   -> save all commands matching regular expression search
        """

        search = None
        narg = None
        args = None
        # defaults: last read file, or default name;
        fn = self.script if self.script else self.script_default  # 'script.scrape'
        if arg:
            args = arg.rsplit(None, 1)
            # TODO:  This isn't quite right, and maybe not needed:
            # might be any number of args
            # c = args[-1][-1]  # last char
            # if c in '"\'':  # quoted filename; re-scan
            #     args[-1] = arg[-1].rsplit(c, 2)[1]
            if args[0][0] == '-':
                narg = args[0][1:].strip()
                if len(args) > 1: # filename given
                    fn = args[1]
            else:
                fn = args[0]
        if narg:
            try:
                history = self.history.span(narg)
            except IndexError:
                history = self.history.search(narg)
        else:
            history = self.history
        #
        # enforce *.scrape naming for scripts;
        if not fn.endswith('.scrape'):
            fn += '.scrape'

        if args and not len(args) > 1:  #no filename provided
            fn = self.name_overwrite(fn)  # honor overwrite flag;
        with must_open(fn, "w") as f:
            f.write("# " + fn + "; saved on " + time.strftime("%c") + "\n#\n")
            f.writelines([hi + '\n' for hi in history])

    def do_table(self, name):
        '''usage: table [name]
        Start new output table; if no name then output current table
        vars are associated with a table context;
        locals are cleared on change of tables;
        (globals persist across tables)'''
        tables = self.tables
        out = self.svars
        if not name:
            # TODO:  check / update table_name
            #  If no table_name, this is somehow screwed up...
            # Never declared a table_name;
            #  - either just declare a default here;
            #  - if this feels like the effect is too "surprising",
            #    then refuse to write, and issue a message;
            if not tables:
                logger.warn("No table name previously declared; using the name '{}'.".format(self.default_table_name))
                tables.append((self.default_table_name, {}))
                self.table_name = self.default_table_name
            if tables:
                (name, nout) = tables.pop()
                # table name gets current output;
                nout.update(out)  # combine any saved outputs
                self.write_table(name, nout)
                # TODO:  if this is the last table
                #  and it's not interactive mode, then we're done.
                # if tables, resume saved output
                ##
                # handle case where tables.pop() left us empty tables:
                out = tables[-1][1] if tables else {}
        else:
            if tables:  # save pending output
                # TODO:  going to need to rethink this:
                # TODO:  going to also need to save key-order
                tables[-1][1].update(out)
            tables.append((name, {}))
            self.table_name = name  # for show command
            # TODO:  revamp anything address "out" w.r.t. var class / structure;
            self.svars = {}
            self.table_ordered_keys = []

        self.history_append("table " + name)


    def do_var(self, arg):
        '''var:
        Declare new variable to scrape into,
        or move an existing variable from one scope to another.

        There are several types of vars:

        local   - values persist per input file / source.
                - not marked for output (although you can at any time alter this);
        global  - persist per session (accross input sources);
                - could be useful, for example, to hold a publication name
                - which will persist over several issues of bibliographic scraping.
        var     - these are vars which are set for output. they persist per table.

        see also: local, global.
        '''
        self.nvar('var', arg)

    def do_local(self, arg):
        '''local:
        Declare new variable to scrape into,
        or move an existing variable from one scope to another.

        There are several types of vars:

        local   - values persist per input file / source.
                - not marked for output (although you can at any time alter this);
        global  - persist per session (accross input sources);
                - could be useful, for example, to hold a publication name
                - which will persist over several issues of bibliographic scraping.
        var     - these are vars which are set for output. they persist per table.

        see also: var, global.
        '''
        self.nvar('local', arg)

    def do_global(self, arg):
        '''global:
        Declare new variable to scrape into,
        or move an existing variable from one scope to another.

        There are several types of vars:

        local   - values persist per input file / source.
                - not marked for output (although you can at any time alter this);
        global  - persist per session (accross input sources);
                - could be useful, for example, to hold a publication name
                - which will persist over several issues of bibliographic scraping.
        var     - these are vars which are set for output. they persist per table.

        see also: var, local.
        '''
        self.nvar('global', arg)

    def do_clear(self, line):
        '''usage:  clear var [var]
        Clear the value of the named variables (if they exist).'''
        # only clear if the var exits
        args = line.split()
        for arg in args:
            if arg in self._sv:
                self.nvar('clear', arg)

    def nvar(self, argtype, arg):
        # Note: vars get put in var_name;
        #       locals get put in local_name;
        #       globals in global_name;
        # If argtype 'clear', clear a var's value (assumes it exists)

        if arg:
            ordered_keys = lambda a: a   # essentially, a no-op
            # if the value exists in some other scope, simply move it
            val = []
            clearing = argtype.startswith('c')

            if clearing:
                nvars = self._sv[arg]
            elif argtype.startswith('l'):  # locals
                nvars = self.slocals
            elif argtype.startswith('g'): # globals
                nvars = self.sglobals
            else:                  # output (scrape) vars
                nvars = self.svars
                ordered_keys = lambda a: self.table_ordered_keys.append(a)

            # if it already exists, we move it's value, i.e. re-scope it;
            if arg in self._sv and not clearing:
                val = self._sv[arg][arg]
                del self._sv[arg][arg]

            # don't change current var if just clearing;
            if not clearing:
                self.var_name = arg
                # scope info:
                self._sv[arg] = nvars

            nvars.update({arg: val})
            ordered_keys(arg)

            # what do I really want on the stack?
            self.cmd_trace.append((arg, val))  # store output(s) in a list
            # reset this:
            if self.preserve_node == False:
                # lxml html parser grabs the head info, and parses it into docinfo
                #  for us;  the only thing "above" the body subtree, is "html"
                #  so there's no sense getting / doing anything else.
                # self.node = self.doc.body
                self.node = self.doc
            self.preserve_node == True
        else:  # nothing to do, really: output held in "out" dict;
            self.var_name = None
        self.history_append(argtype + " " + arg)

    # TODO:
    #  set out = ''
    #    fails:
    '''
        [S]crape >>> set out = ''
        Traceback (most recent call last):
          File "scrape.py", line 1896, in <module>
            main.cmdloop()
          File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/cmd.py", line 142, in cmdloop
            stop = self.onecmd(line)
          File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/cmd.py", line 221, in onecmd
            return func(arg)
          File "scrape.py", line 965, in do_set
            "uplugin['" + rv[m.regs[1][0]:m.regs[1][1]] + "']." + \
        AttributeError: 'NoneType' object has no attribute 'regs'
    '''
    #  set var = ''
    #    fails:
    '''
        [S]crape >>> set session = ''
        Traceback (most recent call last):
          File "scrape.py", line 2073, in <module>
            n = 0
          File "scrape.py", line 344, in main
            scrape.cmdloop()
          File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/cmd.py", line 142, in cmdloop
            stop = self.onecmd(line)
          File "/Library/Frameworks/Python.framework/Versions/2.7/lib/python2.7/cmd.py", line 221, in onecmd
            return func(arg)
          File "scrape.py", line 1125, in do_set
            # - eval & run
        AttributeError: 'NoneType' object has no attribute 'regs'
    '''

    # Need to test deleting things  (set =)? as well as handling
    #  an alias for "out"
    # Also, more generally test this;

    def do_set(self, line):
        """set:

        WARNING: under development (pre-alpha, unstable).

        set a variable, or set of variables to a value (or return from a function).

        - the left variables (comma separated) will be created if they don't exist;
        - the right values or functions must return
            the same number of values as on the left...
            but not enforced, so use caution! behavior:
            - too few returns, left side values empty;
            - excess return values ignored;
        - the right and left sides are separated by '=', an equals-sign.
        - scrape vars used on the right must be written as
            => var['name'], or local['name']
            according to how the variable was declared;
            e.g. for authors =>  var['authors']
            (globals need to be refered to as sglobal['name'],
             since *global* and *globals* are reserved words in Python).

        - currently, only a single plugin call can exist on the right
            (use multiple "set"s to make multiple plugin calls);
        """
        try:
            # ValueError: also catches two '=' signs
            lv, rv = line.split('=')
        except ValueError as e:
            logger.error("invalid set command format:({}) {}".format(e.errorno, e.strerror))
            return
        except:
            logger.error("unknown error: {} - {}".format(sys.exc_info()[0], sys.exc_info()[1]))
            return

        # check that the lv are valid python named vars
        if not self.is_validname.match(lv):
            logger.error("invalid left side assignment expression.")
            return

        # now split left side, validate right side:
        if lv.count(',') > 0:
            lvars = [i.strip() for i in lv.split(',')]
        else:
            lvars = [lv.strip()]
        for i in lvars:
            if not i in self._sv:
                self.svars.update({i: []})
                self.table_ordered_keys.append(i)
                self._sv[i] = self.svars

        # validate right side:
        # - check for plugin call;
        # - convert form of plugin call;
        # - eval & run
        var = self.svars  # for user specifying scrape vars;
        local = self.slocals
        sglobal = self.sglobals

        rv = rv.strip()
        # TODO:  Check if a value, or what...
        m = self.plugin_call.search(rv)
        # now: m.groups() gives the 3 groups: plugin_name, plugin_func, params
        # and: m.regs gives the loc'n in rv of (entire match, the 3 groups)

        # pylint: disable=line-too-long

        # make it easier to see that we're evaling the right string:
        # example:
        #  [S]crape >>> set author_lastname, author_affiliations = affiliations.jama( var['authors'], var['affiliations'] )
        #  _s: "uplugin['affiliations'].jama( var['authors'], var['affiliations'] )"

        # pylint: enable=line-too-long

        _s = rv[:m.regs[0][0]] + \
                "uplugin['" + rv[m.regs[1][0]:m.regs[1][1]] + "']." + \
                rv[m.regs[2][0]:m.regs[0][1]]

        plugrtn = eval(_s)

        if not isinstance(plugrtn, (list, tuple)):
            plugrtn = [plugrtn]
        ## THE IDIOM:
        #  for i,v in enumerate(foo()):
        #    if isinstance(v, (list, tuple)):
        #      self.svars[lvars[i]].extend(v)
        #    else:
        #      self.svars[lvars[i]].append(v)
        #  where foo() is converted to a function call (assume plugin call) thus:
        #      a.b() =>  uplugin['a'].b()
        #  and the entire right-side is eval'd.
        for i, v in enumerate(plugrtn):
            il = lvars[i]
            if isinstance(v, (list, tuple)):
                self._sv[il][il].extend(v)
            else:
                self._sv[il][il].append(v)
        self.history_append("set " + line)


    # Here-on, the commands are split into:
    # - dispatchers (function names starting w/ "do_"), and
    # - processors, by class of function.

    # DISPATCHERS:
    def do_cssselect(self, line):
        '''usage:  cssselect [cssselector strings]

        Find a node by cssselector. Comma separated expressions will find all
        of each term.
        Alias:  select
        
        A quick (incomplete) cheat sheet:

        DIV.warning	Language specific. (In HTML, the same as DIV[class~="warning"].)
        E#myid	Matches any E element with ID equal to "myid".
        *	Matches any element.
        E	Matches any E element (i.e., an element of type E).
        E F	Matches any F element that is a descendant of an E element.
        E > F	Matches any F element that is a child of an element E.
        E + F	Matches any F element immediately preceded by a sibling element E.
        E:first-child	Matches element E when E is the first child of its parent.
        E:link
        E:visited 	Matches element E if E is the source anchor of a hyperlink
                        of which the target is not yet visited (:link) or already visited (:visited).
        E:lang(c) 	Matches element of type E if it is in (human) language c
                        (the document language specifies how language is determined).
        E[foo]	Matches any E element with the "foo" attribute set (whatever the value).
        E[foo="warning"]	Matches any E element whose "foo" attribute value
                                is exactly equal to "warning".
        E[foo~="warning"]	Matches any E element whose "foo" attribute value
                                is a list of space-separated values, one of which is exactly equal to "warning".
        E[lang|="en"]	Matches any E element whose "lang" attribute has
                        a hyphen-separated list of values beginning (from the left) with "en".
        '''
        self.getnodes('cssselect', line)

    do_select = do_cssselect

    def do_find(self, line):
        '''find: find a node by xpath descriptor (see http://www.w3schools.com/xpath/xpath_syntax.asp)'''
        self.getnode('find', line)

    def do_find_by_text(self, line):
        '''usage: find_by_text [xpath] [text to match]

        find a node by an xpath prefix and a text component;

        Example:
             find_by_text .//em This is the string

        will set the current node(s) to which the string belongs (if any)
        which contain any of the text component, under the xpath specified.

        Any substring will match, so if the string "string" is specified, "This is the string" would be found also.

        If an optional number, or range is added, then that node (or those nodes) will be returned.
        Example:
            find_by_text 1 .//em This is
        will return the second resulting node (zero indexing;  0 will return the first resulting node).

        Example:
            find_by_text 0:1 .//em This is
        will return the first two elements.

        findtext is an alias for find_by_text.
        '''
        # Example code for accomplishing this:
        # matching = [s for s in self.root.xpath('.//em/text()') if "Study concept and design" in s]
        # nodes = [i.getparent() for i in matching]

        # Check for a range selector:
        range = ranges = None
        if line.strip()[0].isdigit():
            range, line = line.split(None, 1)
            if ':' in range:
                ranges = range.split(':')
                ranges[0] = int(ranges[0]) if ranges[0] else None
                ranges[1] = int(ranges[1]) if ranges[1] else None
                if all([isinstance(i, int) for i in ranges]):
                    ranges.sort()
            else:
                range = int(range)

        # now, split out the xpath from the string:
        result = line.split(None, 1)   # do this in case insufficient params
        if len(result) != 2:
            logging.error("incorrect number of parameters")
            return
        path, matchstr = result[0]+"/text()", result[1]

        matching = [s for s in self.node.xpath(path) if matchstr in s]

        mn = len(matching)
        if mn == 0:
            logging.warn("No matches found.")
        # It's OK to have the upper range "out of range"; harmless in python;
        # It's also OK to have the lower range "out of range", but it will return an empty list
        if mn > 0 and ranges and ranges[0] and mn < ranges[0]:
            logging.warn(
                "range [{}:{}] lower bound is less than # of matches ({});\n".format(ranges[0], ranges[1], mn)) \
               +"\tresult will merely be an empty list - consider changing or dropping the range."

        if ranges:
            nnodes = [i.getparent() for i in matching[ranges[0]:ranges[1]]]
        else:
            nnodes = [matching[range].getparent()] if range else [i.getparent() for i in matching]

        # TODO:
        # now, display what we found, and set node to the list, as you would in findall;

        if ranges:
            if not ranges[0]:
                which = "to {}".format(ranges[1])
            elif not ranges[1]:
                which = "from {}".format(ranges[0])
            else:
                which = "from {} to {}".format(ranges[0], ranges[1])
        elif range:
            which = "{}".format(range)
        else:
            which = "all"
        if len(nnodes) > 0:  # don't clobber node if we didn't get anything!
            logger.info("result: {} matches found; {} selected".format(mn, which))
            self.node = nnodes
        else:
            logging.warn("No matches selected (current node not changed).")
        self.history_append("find_by_text " + line)

    do_findtext = do_find_by_text

    # TODO:  is this useful here?  Requires an xpath
    def do_getnext(self, line):
        "getnext: get the next sibling node of the current node;"
        self.getnode('getnext', line)

    def do_getparent(self, line):
        "getparent: get the parent of the current node."
        self.getnode('getparent', line)

    def do_getprevious(self, line):
        '''getprevious: get the previous sibling node of the current node; '''
        # TODO: If no xpath expression provided, the last xpath expression is used.
        self.getnode('getprevious', line)

    def do_getbyid(self, line):
        '''getbyid:  get a node by css id.

        get_element_by_id is an alias for getbyid.
        '''
        self.getnode('get_element_by_id', line)

    do_get_element_by_id = do_getbyid

    def do_findall(self, line):
        "findall: find all nodes which match an xpath."
        self.getnodes('findall', line)

    def do_findclass(self, line):
        '''findclass: find by class name.

        find_class is an alias for findclass.
        '''
        self.getnodes('find_class', line)

    do_find_class = do_findclass

    def do_getchildren(self, line):
        "getchildren: get children of current node."
        self.getnodes('getchildren', line)

    def do_search(self, line):
        # pylint: disable= anomalous-backslash-in-string
        """usage:  search  [-next | -offset] regular_expression

        Return nearest context encompasing the first instance of the text searched for.
        Note that this is not the same or the source html (spacing will be different);
        The currently parsed HTML tree is converted to (non-pretty) string, and searched.

        -n, -next   shorthand for continuing the search
                    after the location of the last match
                    (only useful for repeating a search);
        -offset     search node from integer offset;
                    useful to continue searching (where you want
                    to modify the start point)

        The current node is searched.  If you want to search the entire body, or doc,
        then use the 'body' or 'doc' commands to set the current node before searching.

        Notes:
        - search only returns text within the current node;
        - search returns the index (start:end) of the search match;
            you can use the "end" index to set the starting point for
            further searches;
        - be cautious with regular expressions, e.g. Arg*  will match
           the first 'Arg' position in your node, all the way to the end
           of the node;  better to specify any word-character, e.t. Arg\w*;
           see http://docs.python.org/library/re.html for more information.
        - once you've found your search, use the 'mark' command to ensure
           you can find it in the parse tree. See 'help mark' for more.
        """
        # pylint: enable= anomalous-backslash-in-string

        #  I think so, but...
        # node = self.node[0]
        node = self.node
        start = 0
        ### command options:
        # TODO:  use argparse for per-cmd option processing... eventually...
        # get the appropriate node
        if line.startswith(('-n', '-')):
            # If -n and regex, then start from the last anchor point;
            if line.startswith(('-n ', '-next ', '--next ')) \
              or re.search('^-[0-9]+ ', line):
                n = line.find(' ')
                if line[1] == 'n':
                    start = self._search_anchor
                    # does it make sense to ensure the previous node??
                    node = self._search['node']
                else:
                    start = int(line[1:n])
                line = line[n+1:]
            # if just -n, then reuse everything from last time;
            elif line == '-n':
                line = self._search['line']
                node = self._search['node']
                start = self._search_anchor
            else:
                logger.error("Unreconized search option: {}".format(line))
                return

        ###
        nodestr = etree.tostring(node, encoding='unicode')[start:]

        # try with a RE search first - multiline;
        match = re.search(line, nodestr, re.M)
        if match:
            (mstart, mend) = match.span()
            matches = re.findall(line, nodestr)
        # if no match, then fall back: attempt a simple find:
        else:
            mstart = nodestr.find(line)
            if mstart >= 0:
                mend = mstart + len(line)
                # escape the line:
                search_string = line.encode('unicode-escape')
                # matches = re.findall(re.escape(line), nodestr)
                matches = re.findall(search_string, nodestr, re.M)
            # TODO:  actually, we'll be here often:
            #  - from selenium, we get back unicode - think the paragraph mark;
            #  - from etree.tostring
            else:
                # NOTE:  if a grab w/ html, the tags will almost certainly be
                #  in different order, so w/o grab 3 matches extremely unlikely
                # logger.error("searchtext: no match |{}| found in {}".format(line, node))
                line_rep = line[:18]+"..." if len(line) > 18 else line
                logger.error("searchtext: no match |{}| found in {}".format(line_rep, node))
                return
        # save these for marking:
        self._search = {'line':line, 'node':node, 'start': start}
        # TODO:  put this on the args list, so args can be saved / restored
        self._search_anchor = mend
        # try to show the enclosing node's full text for context
        # - n: preceding full tag
        # - m: following full end-tag (not necessarily n's closing tag)
        n = nodestr[:mstart].rfind('>')
        mark_point = n + 1  # so we can spit out the xpath
        n = nodestr[:n].rfind('<')
        m = mend + 1
        m = nodestr[m:].find('</')+m+1
        m = nodestr[m:].find('>')+m+1
        # show the string, w/ context:
        self.stdout.write("----- {}[{}:{}]: -----\n{}\n\n".format(node.tag, mstart, mend, nodestr[n:m]))
        # now, show the xpath leading to this point:
        # - inject an id;
        # - find that id;
        # - get the xpath to it;
        doc = html.fromstring(nodestr[:mark_point] \
                               +"<var id=\"__scrape-mark__\"/>"
                               +nodestr[mark_point:])
        root = doc.getroottree()  # get the etree version
        path_node = doc.get_element_by_id("__scrape-mark__", doc)
        # Stuff to do with the xpath:
        # - add the '.' relative node, because html trees require it.
        # - remove the leading 'html' component: that's our relative parent;
        # - remove the 'var' node we inserted;
        if len(matches) > 0:
            self.stdout.write("{} additional matches found following this one.\n".format(len(matches)-1))
        path = root.getpath(path_node).rsplit('/', 1)[0]
        head = '/html'
        if path.startswith(head):
            path = path[len(head):]
        path = '.'+path
        self.stdout.write("----- xpath: -----\n{}\n\n".format(path))
        # TODO:  may also want to try to parse out a cssselector out of this context.
        #  Potential strategy:
        #  - starting from the scrape-mark:
        #  - work backwards to find the previous 3 (?) nodes containing either id or class

        self.path = path
        self.history_append("search "+line)


    def do_content(self, line):
        '''content: return text of the specified node, and all its children.

        text_content is an alias for content.
        '''
        sl = self.gettext('text_content', line)
        if sl:
            if self.var_name:
                self._sv[self.var_name][self.var_name].extend(sl)
            else:
                logger.info("no current variable; text content is: {}".format(sl))

    do_text_content = do_content

    def do_attrib(self, line):
        '''usage:  attrib attribute_name
        Return the value of the specified attribute of the current node.
        '''
        sl = self.attr('attrib', line)
        if sl:
            # self.svars[self.var_name].append(self.attr('attrib', line))
            #  current_var lambda uses the current type (var/local/global)
            self._sv[self.var_name][self.var_name].extend(sl)

    def do_text(self, line):
        "text:  return the text of the current node."
        sl = self.text('text', line)
        if sl:
            if self.var_name:
                self._sv[self.var_name][self.var_name].extend(sl)
            else:
                logger.info("no current variable; text is: {}".format(sl))

    def do_tail(self, line):
        "tail:  return the tail-text of the current node."
        sl = self.text('tail', line)
        if sl:
            if self.var_name:
                self._sv[self.var_name][self.var_name].extend(sl)
            else:
                logger.info("no current variable; tail text is: {}".format(sl))

    # TODO: I could see extending / adding a 'node' command that provides any attrib
    # of a given node/nodes
    def do_nodes(self, line):
        """nodes: return count of currently selected nodes.
        
           aliases: n, count
        """
        self.stderr.write("{}\n".format(len(self.node)))


    do_n = do_nodes
    do_count = do_nodes


    def do_tags(self, line):
        "tags:  return a list of the current node's html tags."
        t = [i.tag for i in self.node]
        self.stderr.write("{}\n".format(t))


    # PROCESSORS:

    def getnode(self, cmd, arg):
        ""
        # if node is an array, do cmd for each...
        nodes = self.node
        if not isinstance(nodes, list):
            nodes = [nodes]
        # TODO:
        # if arg is not looking like an xpath, then
        #   assume it's a CSS selector - compile to an xpath.
        # narg = csssel_or_xpath(arg)
        nnodes = []  # unix-ish naming: n-name => new-name
        for node in nodes:
            action = getattr(node, cmd, None)
            self.cmd_trace.append([node, (action, arg)])
            try:
                nnode = action() if cmd in noargcall else action(arg)
            except (TypeError, SyntaxError) as e:
                logger.error("{}: you need a valid XPATH here.".format(e))
                return
            if nnode is None or not isinstance(nnode, html.HtmlElement):
                logger.warning("Nothing found in '{}' with XPATH expression '{}'".format(node.tag, arg))
            else:
                nnodes.append(nnode)
                # for logging:
                logger.info("{} {}: {}".format(cmd, arg, nnode))
        if len(nnodes) > 0:
            self.node = nnodes
        self.history_append(cmd + " " + arg)

    def getnodes(self, cmd, arg):
        ""
        # if node is an array, do cmd for each...
        nodes = self.node
        if not isinstance(nodes, list):
            nodes = [nodes]
        nnodes = []  # unix-ish naming: n-name => new-name
        for node in nodes:
            action = getattr(node, cmd, None)
            self.cmd_trace.append([node, (action, arg)])
            try:
                nnode = action() if cmd in noargcall else action(arg)
            except (TypeError, SyntaxError) as e:
                logger.error("{}: you need a valid XPATH here.".format(e))
                return
            if len(nnode) == 0:
                logger.warning("Nothing found in '{}' with XPATH expression '{}'".format(node.tag, arg))
                continue
            nnodes.extend(nnode)
            logger.info("{} {}: {}".format(cmd, arg, [i.tag for i in nnode]))
        if len(nnodes) > 0:  # don't clobber node if we didn't get anything!
            self.node = nnodes
        self.history_append(cmd + " " + arg)

    def gettext(self, cmd, line):
        ""
        var_name = self.var_name
        if var_name is None:
            self.preserve_node = True
            logger.warn(
                "{}: No active output variable to assign to.\n".format(cmd) + \
                "\tDefine one with 'var some_name', or '<some_name>'."
                )
            return
        nodes = self.node
        results = []
        if not isinstance(nodes, list):
            nodes = [nodes]
        for node in nodes:
            action = getattr(node, cmd, None)
            text = action()
            if not text:
                logger.warn("The tree rooted at node '{}' contains no text;".format(node.tag))
                continue
            text = text.strip()
            # Archaic: self.out[var_name].append(text)
            self.cmd_trace.append([node, (action, text)])
            logger.info("%s: %s: '%s'" % (var_name, cmd, text))
            results.append(text)
        self.history_append(cmd + " " + line)
        return results

    def attr(self, cmd, arg):
        "return the value of a node's attribute"

        # var_name is the current variable name -
        #  - but this is all going away to be processed w/in the
        #    variable handling functions
        '''
        var_name = self.var_name
        if var_name is None:
            self.preserve_node = True
            logger.warn(
                "{} {}: No active output variable to assign to.\n".format(cmd, arg) + \
                "\tDefine one with 'var some_name', or '<some_name>'."
                )
            return
        '''
        nodes = self.node
        results = []
        if not isinstance(nodes, list):
            nodes = [nodes]
        for node in nodes:
            action = getattr(node, cmd, None)
            if arg in action:
                # delegate this down to the var assignment:
                '''
                self.out[section].append(action[arg])
                self.cmd_trace.append([node, (action)])
                logger.info("{}: {} {}: '{}'".format(section, cmd, arg, self.out[section][-1]))
                '''
                result = action[arg]
                logger.info("{} {}: '{}'".format(cmd, arg, result))

                # self.stdout.write(result+'\n')
                self.cmd_trace.append([node, (action)])
                results.append(result)
            else:
                self.cmd_trace.append([node, (action)])
                logger.warn("{}: no attribute '{}'".format(node, arg))
        self.history_append(cmd + " " + arg)
        return results

    def text(self, cmd, line):
        ""
        """
        section = self.var_name
        if section is None:
            self.preserve_node = True
            logger.warn(
                "{}: No active output variable to assign to.\n".format(cmd) + \
                "\tDefine one with 'scrape some_name', or '<some_name>'."
                )
            return
        """
        nodes = self.node
        results = []
        if not isinstance(nodes, list):
            nodes = [nodes]
        for node in nodes:
            # if no text, getattr will return None
            action = getattr(node, cmd, '')
            if action is None:
                # TODO:
                logger.warn("Node '{}' contains no text;".format(node.tag))
                continue
            self.cmd_trace.append([node, (cmd, action)])
            logger.info("{}: '{}'".format(cmd, action.strip()))
            results.append(action.strip())
            # if action:
            #     self.out[section].append(action)
        self.history_append(cmd + " " + line)
        return results

    def do_help(self, line=''):
        '''usage:  help [cmd]

        Show help on a command, or list the commands available.

        ? is an alias for help.
        '''

        'If line contains more than one word, pass it to help command'
        args = line.split(None, 1)
        arg = args[0] if args else ''
        if arg:
            # XXX check arg syntax
            try:
                func = getattr(self, 'help_' + arg)
            except AttributeError:
                try:
                    doc = getattr(self, 'do_' + arg).__doc__
                    if doc:
                        self.stdout.write("{}\n".format(str(doc)))
                        return
                except AttributeError:
                    pass
                self.stdout.write("{}\n".format(str(self.nohelp % (arg,))))
                return
            func(args[1:])
        else:
            names = self.get_names()
            cmds_doc = []
            cmds_undoc = []
            help = {}
            for name in names:
                if name[:5] == 'help_':
                    help[name[5:]] = 1
            names.sort()
            # There can be duplicates if routines overridden
            prevname = ''
            for name in names:
                if name[:3] == 'do_':
                    if name == prevname:
                        continue
                    prevname = name
                    cmd = name[3:]
                    if cmd in help:
                        cmds_doc.append(cmd)
                        del help[cmd]
                    elif getattr(self, name).__doc__:
                        cmds_doc.append(cmd)
                    else:
                        cmds_undoc.append(cmd)
            self.stdout.write("{}\n".format(str(self.doc_leader)))
            # pylint: disable=bad-whitespace
            self.print_topics(self.doc_header,   cmds_doc, 15, 80)
            self.print_topics(self.misc_header,  list(help.keys()), 15, 80)
            self.print_topics(self.undoc_header, cmds_undoc, 15, 80)
            # pylint: enable=bad-whitespace


    def do_EOF(self, line):
        '''[EOF]:
        Exit [S]crape.

        Exit interactive mode by typing the End-Of-File <EOF> character on your
        computer.

        [CTRL-D] on many systems; [CTRL-Z] followed by a [RETURN] on Windows operating systems.
        '''
        return True

    def postloop(self):
        self.stdout.write('\n')

    ## history stuff from cmd2:
    #
    def do_history(self, arg): #, opts):
        """usage:  history [arg]

        Lists or runs past scriptable commands.  Also provides the stack
        from which to save developed [S]crape scripts (see "save" for more).

                  no arg:  list all
             integer arg:  list one history item, by index
              string arg:  string search
        /arg in slashes/:  regular expression search

        The "run" command will run the last history selection
           made with either the "history" or "list" commands.

        hi is an alias for history.
        also see list.
        """
        if arg:
            history = self.history.get(arg)
        else:
            history = self.history
        for i in history:
            self.stdout.write(i.pr())

    def do_list(self, arg):
        """list [arg]: lists last command

                    no arg  -> list most recent command
               integer arg  -> list one history item, by index
        a..b, a:b, a:, ..b  -> list spans from a (or start) to b (or end)
                string arg  -> list all commands matching string search
          /arg in slashes/  -> regular expression search

        The "run" command will run the last history selection
           made with either the "history" or "list" commands.

        li is an alias for list.
        also see history.
        """
        try:
            history = self.history.span(arg or '-1')
        except IndexError:
            history = self.history.search(arg)
        for i in history:
            self.poutput(i.pr())

    do_hi = do_history
    do_li = do_list

    def do_run(self, arg):
        """usage: run [arg]

        Runs the commands resulting from the last history or list search.

                    no arg  -> (re)run the most recent command in history
               integer arg  -> (re)run one history item, by index
        a..b, a:b, a:, ..b  -> (re)run a list of commands from history, which
                                span from a (or start) to b (or end)
                string arg  -> (re)run all commands matching string search
          /arg in slashes/  -> (re)run all commands matching regular expression search

        Explicitly (not out of history):
        arg1, arg2, arg... -> run, in order, a comma separated list of commands

        r is an alias for run.
        """
        # not documented; not sure how reliably this will work:
        # Run the comma-separated list of commands in the args
        # TODO: try using shlex here; note that this could mean running scripts
        # (with "source script.scape")
        if arg.find(',') > 0:  # can't start w/ a comma
            history = re.split(r'\s*,\s*', arg)
        else:  # assume it's like list:
            try:
                history = self.history.span(arg or '-1')
            except IndexError:
                history = self.history.search(arg)

        for i in history:
            self.stdout.write('  '+i+'\n')
            self.onecmd(i)

    do_r = do_run

    def poutput(self, msg):
        '''Convenient shortcut for self.stdout.write(); adds newline if necessary.'''
        if msg:
            self.stdout.write(msg)
            if msg[-1] != '\n':
                self.stdout.write('\n')


#---< end of Cmd class >---#


### lifted from cmd2:
# History stuff:
#
class HistoryItem(str):
    # listformat = '-------------------------[%d]\n%s\n'
    listformat = '[{:3d}]\t{}\n'
    def __init__(self, instr):
        str.__init__(self)
        self.lowercase = self.lower()
        self.idx = None
    def pr(self):
        return self.listformat.format(self.idx, str(self))

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
        if not isinstance(raw, (str, unicode)):
            raise IndexError
        if self == [] or self == ['']:  # short circuit this boundary
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
                    return getme.lower() in hi.lowercase
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
    _use_user_profile = False  # by default
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
    def close(self):
        if Driver._browser:
            Driver._browser.close()
        if Driver._viewer:
            Driver._viewer.close()

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

                    MSG_NO_PROFILE = "Can't find your Firefox profiles configuration."
                    config = ConfigParser.ConfigParser()
                    config.read(prof)
                    pth = None
                    for i in config.sections():
                        if config.has_option(i, 'name') \
                           and config.get(i, 'name').lower() == 'default' \
                           and config.has_option(i, 'path'):
                            pth = config.get(i, 'path')
                            if config.has_option(i, 'isrelative'):
                                rltv = config.get(i, 'isrelative').startswith(('1', 'y', 'Y'))
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

URL_HEAD = ('about:', 'http://', 'https://', 'file:///')
URL_TYPO = ('http:', 'htp', 'htpp', 'http', 'file')

def open_tree(fn, headless=False):
    # if fn is a file path, try to read it with html.parse(),
    #  but we'll have missing functionality;
    # if fn is a url, or starts with "file:///...", then use
    #  selenium to open, unless --batch mode.

    def _parse_page_source(page, name):
        try:
            node = html.fromstring(page)
        except ValueError as e:  # parse syntax error, such as on empty page:
            if CONTAINS("encoding", e.message):
                logger.warn(
                "\nURL: {}:\nWarning: {}\nscrape: will attempt to remove encoding declaration and re-parse..."\
                        .format(name, e.message))
                epage = re.sub('encoding="[^"]*"', '', page)
                try:
                    self.doc = html.fromstring(epage)
                except Exception as e:
                    logger.error("{}".format(e.message))
                    node = None
            else:
                node = None

        return node
    #-----------

    ## TODO:  lots of try/excepts needed here:
    # open the browser; parse the source
    browser = Driver().browser
    # DEBUG:
    # logger.warn("fn: {}; BATCH={!s}; isfile={!s}".format(fn, BATCH, isfile))

    ###  This will not work with many URI's, but leave it to user discretion:
    # if BATCH or (isfile and not fn.endswith('.html')):
    # if (isfile and not fn.endswith('.html')):  # assume we can read it raw???
    #### TODO: move this into a fcn:
    if fn:
        isfile = os.path.isfile(fn)
        if headless:
            try:
                node = html.parse(fn).getroot()
            except IOError as e:   # catch all errors
                opener = build_opener()
                # may not need this, but we'll set it anyway:
                opener.addheaders = [('User-agent', 'Mozilla/5.0')]
                try:
                    f = opener.open(fn)
                    page = f.read()
                except Exception as e:
                    logger.error("Failed to open {}: {}".format(fn, e.message))
                    raise
                finally:
                    f.close()
                node = _parse_page_source(page, fn)
            except:  # catch all
                e = sys.exc_info()
                logger.error("Unexpected error {}: {}".format(e[0], e[1]))
                raise
            return node
    
        if isfile:  # convert it to a URI
            nfn = 'file:///' + os.path.abspath(fn)
            fn = nfn
    
        if not fn.startswith(URL_HEAD):
            if not fn or fn.startswith(URL_TYPO):
                msg = "No URI path or invalid path provided;"
                logger.warn(msg)
                return None
            elif fn == 'about':
                fn = fn + ':'
            else:
                msg = "Invalid URI: {} (protocol missing); adding 'http://'".format(fn)
                logger.warn(msg)
                fn = 'http://'+fn
        # only if we're dealing with a URI, do we get it;
        # - otherwise we get the current_url in the current browser.
        browser.get(fn)  # load URI into browser

    # else:  no filename given, use current browser url:
    page = browser.page_source
    return _parse_page_source(page, browser.current_url)

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
        logger.error('Unable to open: {}\n'.format(e))
        # exit(2)
        raise
    return fp


def roll_name(f):
    n = 0
    nf = f
    sf = os.path.splitext(f)
    while os.path.exists(nf):
        n += 1
        if n > 99:
            logger.error('Unable to open {} - too many files by that name!'.format(f))
            # exit(2)
            raise IOError
        nf = sf[0] + "-{:d}".format(n) + sf[1]
    return nf

###


if __name__ == '__main__':
    # get parameters:
    main()

