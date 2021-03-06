# -*- coding: utf-8 -*-
#
# This file is part of INGInious. See the LICENSE and the COPYRIGHTS files for
# more information about the licensing of this file.

""" A demo plugin that adds a page """
import logging


class DemoPage(object):
    """ A simple demo page showing how to add a new page """

    def GET(self):
        """ GET request """
        return "This is a test page :-)"


def init(plugin_manager, _, _2, _3):
    """ Init the plugin """
    plugin_manager.add_page("/test", "webapp.plugins.demo_page.DemoPage")
    logging.getLogger("inginious.webapp.plugin.demopage").info("Started Demo Page")
