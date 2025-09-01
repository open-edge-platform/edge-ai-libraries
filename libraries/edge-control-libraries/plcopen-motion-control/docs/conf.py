# SPDX-FileCopyrightText: (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

"""PLCopen Motion Control Documentation"""

import os

# import common documentation config
from docconf import docconf

# sphinx doesn't use UPPER_CASE naming style for constants
# pylint: disable=invalid-name


###### Common variables from docconf ######
#
# You generally should *not* override or replace the values below -  instead
# make changes to the docconf module - see the repo README for further
# instructions.

version = docconf.version
release = docconf.release
project = docconf.project
author = docconf.author
copyright = docconf.copyright  # pylint: disable=redefined-builtin

warning_is_error = docconf.warning_is_error

extensions = docconf.extensions

templates_path = docconf.templates_path
exclude_patterns = docconf.exclude_patterns

source_suffix = docconf.source_suffix
source_encoding = docconf.source_encoding

language = docconf.language
master_doc = docconf.master_doc
rst_epilog = docconf.rst_epilog
myst_substitutions = docconf.myst_substitutions

autosectionlabel_prefix_document = docconf.autosectionlabel_prefix_document
autosectionlabel_maxdepth = docconf.autosectionlabel_maxdepth

linkcheck_ignore = docconf.linkcheck_ignore
linkcheck_request_headers = docconf.linkcheck_request_headers
linkcheck_timeout = docconf.linkcheck_timeout
linkcheck_retries = docconf.linkcheck_retries
linkcheck_exclude_documents = docconf.linkcheck_exclude_documents

spelling_word_list_filename = docconf.spelling_word_list_filename
spelling_filters = docconf.spelling_filters
spelling_exclude_patterns = docconf.spelling_exclude_patterns

html_theme = docconf.html_theme

html_baseurl = docconf.html_baseurl
html_favicon = docconf.html_favicon
html_static_path = docconf.html_static_path
html_show_sourcelink = docconf.html_show_sourcelink
html_show_sphinx = docconf.html_show_sphinx

html_context = docconf.html_context
html_theme_options = docconf.html_theme_options

# Configure myst_parser (only used by docconf_simple)
myst_heading_anchors = docconf.myst_heading_anchors
suppress_warnings = docconf.suppress_warnings
myst_enable_extensions = docconf.myst_enable_extensions
