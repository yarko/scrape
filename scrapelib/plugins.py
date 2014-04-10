#
# plugins.py - a simple plugin loader for scrape
#
# 2012 - Yarko Tymciurak
#   patterned after the incredibly simple:
#   http://pytute.blogspot.com/2007/04/python-plugin-system.html

import os
## I don't think we need these:
# import os.path
# import imp   # to find other modules
import inspect
import sys
import logging


#def load_plugins():
def load(logger):
    # Setup 3 import paths:
    # - installation directory;
    # - user's home space;
    # - CWD, that is active project directory;
    #
    
    # set up the level for loading plugings:
    for i in logger.handlers:
        # get the first StreamHandler:
        if isinstance(i, logging.StreamHandler):
            handler = i
            old_handler_level = i.level
            handler.setLevel(logging.INFO)
            break
    
    old_log_level = logger.getEffectiveLevel()
    logger.setLevel(logging.INFO)
    #

    PLUGIN_DIR = '/_scrape/plugins'
    # In each, expect "_scrape/plugins/" as the local path for plugins;
    # Process each path in order, so that:
    #  -project overrides user which overrides default installation
    #
    # Expect each plugin to have a "register" function
    #   (we don't want to depend on class init's; plugins don't really need to be classes);

    # get - installation directory;
    #  To get the outerframes, inspect.getouterframes(fr), for a particular frame,
    #    or inspect.stack() for the current frame, which returns an array of values,
    #    whose indecies are:
    #FRAME = 0
    # The remaining here represent inspect.getinfo(frame)
    FILENAME = 1   # FILENAME is the only one I'm using, below
    #LINE_NUMBER = 2
    #FUNCTION_NAME = 3
    #LINES = 4  #  <== an array of strings containing the calling lines
    #INDEX = 5  # the relevant code line number w/in the provided context (or 0)

    #  usually, the calling frame will be [1], and we want its FILENAME;
    #     When trying from the Debug Probe w/ wing this jumps by +6, (i.e. +7)
    CALLER = 1
    script_name = inspect.stack()[CALLER][FILENAME]
    script_path = os.path.dirname(os.path.abspath(script_name))

    # get - user's home space;
    home = os.environ["HOME"] if "HOME" in os.environ else None

    # get - CWD, that is active project directory;
    cwd = os.getcwd()

    pluginpaths = [i+PLUGIN_DIR for i in [script_path, home, cwd] if i is not None]
    pluginpaths = [i for i in pluginpaths if os.path.exists(i)]

    for pth in pluginpaths:
        if pth and not pth in sys.path:
            # insert these at the front of sys.path;
            # The effect it that cwd (inserted last)
            #  will be searched first, and so on...
            sys.path.insert(0, pth)

    # Get the module names from *.py files in the pluginpaths directories;
    #  - use dict-comprehension to limit to one module load
    #    (path heirarchy determines which)
    #  Note: setup puts __init__.py in the installation directory, so we ignore it always.
    pluginmodules = {f[:-3]:'' for p in pluginpaths for f in os.listdir(p) \
                     if (not f.startswith("__init__") and f.endswith(".py"))}.keys()
    # Not sure if this is needed:
    #  With sys.modules['string'], we can find it.
    #  With this, we get a list of the imports (otherwise no partiularly good way to find from sys.modules)
    imported_plugins = [__import__(f) for f in pluginmodules]

    # now try to register them all;
    #  - IFF no 'register()' in a module, remove it.
    if len(imported_plugins)>0:
        logger.info("...registering plugins:")
    for mod in imported_plugins:
        if 'register' in dir(mod):
            try:
                # give the plugin the program logger to use:
                mod.register(logger)
                logger.info("\t\t{}".format(mod.__name__))
            except:
                del( sys.modules[mod.__name__] )
                logger.info("FAILED plugin:\t{}".format(mod.__name__))
        else:
            logger.info("BAD plugin:\t{}".format(mod.__name__))
            del( sys.modules[mod.__name__] )

            # TODO:
            # log a warning about this;
            # or at least return some indicator

    # And finally:
    handler.setLevel(old_handler_level)
    logger.setLevel(old_log_level)
    
    return {i.__name__: i for i in imported_plugins}

