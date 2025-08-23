"""
Configuration file for the Sphinx documentation builder.

For the full list of built-in configuration values, see the documentation:
https://www.sphinx-doc.org/en/master/usage/configuration.html
"""

import os
import sys
from datetime import datetime

# Add the project root directory to the Python path
sys.path.insert(0, os.path.abspath(".."))
sys.path.insert(0, os.path.abspath("../src"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Memoir"
copyright = f"{datetime.now().year}, Memoir Contributors"
author = "Memoir Contributors"

# The full version, including alpha/beta/rc tags
# Import version from the package
try:
    from memoir import __version__

    release = __version__
except ImportError:
    release = "0.1.0"

version = release

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.coverage",
    "sphinx.ext.githubpages",
    "sphinx_autodoc_typehints",
    "myst_parser",
]

# Add support for Markdown files
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
    "show-inheritance": True,
}

autodoc_typehints = "description"
autodoc_typehints_format = "short"

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True

# Intersphinx mapping to other documentation
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    # Disable problematic intersphinx mappings for now
    # "pydantic": ("https://docs.pydantic.dev/2.0", None),
    # "langchain": ("https://python.langchain.com/docs/", None),
}

# Templates path
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]

# Logo configuration
html_logo = "_static/memoir.png"
html_favicon = "_static/memoir.png"

# Custom CSS
html_css_files = [
    "custom.css",
]

# Theme options
html_theme_options = {
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

# -- Options for LaTeX/PDF output --------------------------------------------

latex_elements = {
    "papersize": "letterpaper",
    "pointsize": "10pt",
    "preamble": "",
    "figure_align": "htbp",
}

# Grouping the document tree into LaTeX files
latex_documents = [
    ("index", "memoir.tex", "Memoir Documentation", "Memoir Contributors", "manual"),
]

# -- Extension configuration -------------------------------------------------

# MyST parser configuration for Markdown support
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "html_image",
    "replacements",
    "smartquotes",
    "substitution",
    "tasklist",
]
