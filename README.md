# scrape.py README:

Status:  alpha  (useable / useful , but messy code, and probably not very uniform nor reliable in behavior; )

This project evolved from a custom scraping program for researchers, into a tool which would not be too terribly difficult to use by non-programmers, yet satisfying in some ways for programmers.  University of Chicago allowed me to open-source it.

[S]crape is a python based command line tool with shell interface and some rudimentary plugins (plugin system needs *love*, or update).  It uses lxml and uses selenium for an interactive web head, but can also be operated in headless fashion.  Mozilla Firefox is supported (which is the python driver from selenium), but you may be able to use it with other web browsers.

It has a search facility, and tries to provide you with match (or selection)  paths so you can interactively affect your context view.

Tutorials and installation instructions can be found on [scrape.readthedocs.org](http://scrape.readthedocs.org).

## Future Directions

Search functions suffer from different ordering of elements and trees as retreived by selenium (during interactive).

- [ ] try adapting something like scrapinghub's portia approach in place of current use of selenium;
- [ ] use pandas for scraping results - viewing & saving;
- [ ] update plugin structure;
  - [ ] Doug Hellman's `cliff` may be the perfect vehicle - port to `cliff`;
- [ ] add timing (hit frequency) control to running script;
- [ ] consider running background (long running) spider for scripts;
- [ ] port to Python-3.4+
