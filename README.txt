scrape.py README:

Project todo's / activity:
  https://trello.com/board/extended-author-info-scrape/4ff30ef5778bdff73b1c7902

Thu Jul 26 11:05:48 CDT 2012
----
scrape.py is the current target application.
Status:  pre-alpha  (useable / useful by development staff)

This project has evolved from jco-scrape.py (exploring the lxml html extensions),
to scrape2stata.py - which attempted to use a CONFIG file for specifying what to
scrape.   The CONFIG file was a failed attempt, since CONFIG sections are not
ordered (you cannot depend on the order the lines will be processed).

In considering the options, 3 presented themselves:
- parse manually;
- write a grammar / language (e.g. using a parser tool, such as ply)
- try to write a simple command processor to manage the commands.

Current attempt is with the command processor, for a few reasons:
- it's the simplest option;
- there exists a library to implement cmd processors;
- it holds potential to offer an interactive environment to develop scraping steps;
- it holds the option (thru examples such as cmd2) to add shell and python statement
  processing into the mix.

