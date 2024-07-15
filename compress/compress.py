#!/usr/bin/python3

#  Copyright (C) 2021-2023 Rafael Senties Martinelli. All Rights Reserved.

DEBUG = False

static = "/home/cadweb/cadweb/core/static/"
TEMPLATES_PATH = "/home/cadweb/cadweb/core/templates/"
INTEGRITY_FILE = "/home/cadweb/cadweb/core/django/cadweb/integrity.py"
INTEGRITY_KEY_REMOVAL = "/home/cadweb/cadweb/core/static/"
GIT_VERSIONING = True
MD5_VERSIONING = True  # MD5 overrides GIT versioning

IGNORED_INCLUDE_STRINGS = [".git"]
DONT_COMPRESS_PATHS = ["external/", "fontawesome-free/"]

_INFO_TAG = "@GENERATION_INFO"  # to be avoided if using the HTML5 integrity value (because of the dateime-hour)
_INCLUDE_JS = "includeJS:"
_INCLUDE_CSS = "includeCSS:"
_INCLUDE = "include:"
_REDUCE_PUBLIC_JS = "reducePublicJSExcept:"

import re
import os
import subprocess
import sys
from hashlib import sha384, md5
from base64 import b64encode

project_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, project_path)
os.chdir(project_path)

from datetime import datetime

from jsmin import jsmin
from cssmin import cssmin
from reduce_js import reduce_js

INTEIGRY_DICT = {}

def __get_git_revision_short_hash():
    return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()

if MD5_VERSIONING:
    _VERSIONING_VALUE = None
elif GIT_VERSIONING:
    _VERSIONING_VALUE = __get_git_revision_short_hash()
else:
    _VERSIONING_VALUE = None

INTEGRITY_TEMPLATE = """#!/usr/bin/python3

# this file is dynamically generated, do not modify it by hand.

class StaticFile:
    def __init__(self, file_sha384, static):
        self.integrity = "sha384-"+file_sha384
        self.static = static
    
    def __str__(self):
        return "[{{}},{{}}]".format(self.static, self.integrity)

_GIT_VERSIONING = {}

_INTEGRITY_DICT = {}
"""


class StaticFile:
    def __init__(self, file_sha384, static_f):
        self.sha384 = file_sha384
        self.integrity = "sha384-" + file_sha384
        self.static = static_f


def __path_from_path(line, tag):
    return line.split(tag, 1)[1].strip()

def __hash_file(system_file_name, compressed_file_path, dictionary, verbose):
    with open(system_file_name, 'rb') as f:
        file_sha384 = b64encode(sha384(f.read()).digest()).decode("utf-8")

    integrity_key = compressed_file_path.replace(INTEGRITY_KEY_REMOVAL, "", 1).replace("/", "_").replace("-",
                                                                                                         "_").replace(
        ".", "_").lower()

    static_f = "/static/" + system_file_name.split("static/")[1]

    dictionary[integrity_key] = StaticFile(file_sha384, static_f)

    if verbose:
        print("\tkey:\t\t" + integrity_key)
        print("\tstatic:\t\t" + static_f)
        print("\tsha384:\t\t" + file_sha384)
        print()


def __remove_comments(text):
    #
    # Remove JS comments /* */
    #

    text_items = []

    inside_comment = False
    for char in re.split(r'(\s+)', text):

        if char.startswith("/*"):
            inside_comment = True

        elif char.endswith("*/"):
            inside_comment = False

        elif not inside_comment:
            text_items.append(char)

    new_text = "".join(item for item in text_items)

    #
    # Remove JS comments starting with //
    # But do not remove strings:  'https://'
    #
    comment_chars = ("'", '"')

    text_items = []
    for line in new_text.split("\n"):

        if "//" in line:

            keep_items = []
            comment_char = None

            for splitted_char in re.split(r'([\s\'\"])', line):

                if splitted_char in comment_chars and comment_char is None:
                    comment_char = splitted_char
                    keep_items.append(splitted_char)

                elif splitted_char == comment_char:
                    comment_char = None
                    keep_items.append(splitted_char)

                elif "//" in splitted_char and comment_char is None:
                    splitted_char = splitted_char.split("//")[0]
                    keep_items.append(splitted_char)
                    break

                else:
                    keep_items.append(splitted_char)

            line = "".join(item for item in keep_items).strip()

        text_items.append(line)

    new_text = "\n".join(item for item in text_items)

    return new_text


def compress_directory(minify=True, reduce=True, verbose=True):
    print("\nCompressing static files (minify={}, reduce={}, verbose={}):".format(minify, reduce, verbose))

    #
    # Removing old files
    #

    if verbose:
        print("\n************ Deleting ************")
        print("**********************************\n")

    for dirpath, _, filenames in os.walk(static):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dirpath, filename))
            if not any(include_string in file_path.lower() for include_string in
                       IGNORED_INCLUDE_STRINGS + DONT_COMPRESS_PATHS) and (file_path.endswith(".min.js") or
                                                                           file_path.endswith(".min.dict") or
                                                                           file_path.endswith(".min.css")):
                os.remove(file_path)

                if verbose:
                    print(" {}".format(file_path))

                    #
    # Compressing the files
    #

    if verbose:
        print("\n************ Compressing ************")
        print("*************************************\n")

    for dirpath, _, filenames in os.walk(static):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dirpath, filename))

            if any(include_string in file_path.lower() for include_string in
                   IGNORED_INCLUDE_STRINGS + DONT_COMPRESS_PATHS) or not file_path.endswith(".comp"):
                continue

            if verbose:
                print(" " + file_path)

            with open(file_path, "r") as f:
                template_lines = f.readlines()

            compressed_lines = []
            encode_dictionary = ""

            reduce_public_js_except = []
            reduce_public_js = False

            for line in template_lines:

                line = line.replace("\n", "")

                if _INFO_TAG in line:
                    new_line = line.replace(_INFO_TAG, "@Generated at: {}".format(datetime.now()))
                    compressed_lines.append(new_line)


                elif line.startswith(_REDUCE_PUBLIC_JS):

                    reduce_public_js = True

                    exclude_methods = line.split(_REDUCE_PUBLIC_JS, 1)[1]

                    for elem in exclude_methods.split(";"):

                        elem = elem.strip()

                        if elem != "":
                            reduce_public_js_except.append(elem)

                elif line.startswith(_INCLUDE_JS):

                    include_path = __path_from_path(line, _INCLUDE_JS)

                    with open(include_path, 'r') as f:
                        data = f.read()

                    if minify:
                        compressed_data = jsmin(data)

                    elif reduce:
                        compressed_data = __remove_comments(data)
                    else:
                        compressed_data = data

                    compressed_data = compressed_data.replace('"use strict";', "")
                    compressed_data = compressed_data.replace("'use strict';", "")
                    compressed_data = compressed_data.replace(';}', "}")
                    compressed_lines.append(compressed_data)
                    
                    
                    if minify and len(compressed_data.split("\n")) > 1:
                        print("[Info] multiple lines compressing", include_path)
                        for c_line in compressed_data.split("\n"):
                            print("\t"+c_line[:50])
                    


                elif line.startswith(_INCLUDE_CSS):

                    include_path = __path_from_path(line, _INCLUDE_CSS)

                    with open(include_path, 'r') as f:
                        data = f.read()

                    if minify:
                        compressed_data = cssmin(data)
                    else:
                        compressed_data = data

                    # comp_css = cssmin(sys.stdin.read(), wrap=options.wrap)
                    compressed_data = compressed_data.replace("+", " + ").replace("  ", " ")
                    compressed_data = compressed_data.replace('opacity:0', 'opacity: 0')

                    compressed_lines.append(compressed_data)


                elif line.startswith(_INCLUDE):

                    include_path = __path_from_path(line, _INCLUDE)

                    with open(include_path, 'r') as f:
                        read_lines = f.readlines()

                    for read_line in read_lines:
                        compressed_lines.append(read_line)



                else:
                    compressed_lines.append(line)

            file_data = "\n".join(compressed_lines)

            #
            # Rename the file
            #

            compressed_file_path = file_path.rsplit(".comp", 1)[0]

            if MD5_VERSIONING:
                file_name = os.path.basename(compressed_file_path)

                if "." not in file_name:
                    raise ValueError(
                        'Error, invalid filename: It must end with ".js.comp" or ".css.comp" not filename = ' + file_name)
                    exit(1)

                extension = file_name.rsplit(".", 1)[1]

                md5_creator = md5()
                md5_creator.update(file_data.encode())

                system_file_name = "{}/{}.min.{}".format(os.path.dirname(compressed_file_path), md5_creator.hexdigest(),
                                                         extension)

            elif GIT_VERSIONING:
                system_file_name = compressed_file_path.replace(".min.", ".{}.min.".format(_VERSIONING_VALUE))

            else:
                system_file_name = compressed_file_path

            #       
            # Improve the indentation
            #
            file_data = file_data.replace("\t", "    ")  # this will normalize the spaces and place them into the end?
            while "    " in file_data:
                file_data = file_data.replace("    ", "\t")

            #
            # Encode the data
            #

            if reduce and system_file_name.endswith(".js"):
                file_data, encode_dictionary = reduce_js(file_data,
                                                         public=reduce_public_js,
                                                         skip_items=reduce_public_js_except,
                                                         verbose=verbose)

            #
            # Write and Hide the compressed files
            #
            file_name = os.path.basename(system_file_name)
            if not file_name.startswith("."):
                system_file_name = system_file_name.replace("/{}".format(file_name), "/.{}".format(file_name))

            with open(system_file_name, "w") as f:
                f.write(file_data)

            # 
            # Write the encode dictionary
            #
            if reduce and system_file_name.endswith(".js"):
                with open(system_file_name.replace("min.js", "min.dict"), "w") as f:
                    f.write(encode_dictionary)

            #
            # HASH
            #   

            __hash_file(system_file_name, compressed_file_path, INTEIGRY_DICT, verbose)

    #
    # Excluded files
    #

    if verbose:
        print("\n************ Excluded from compression ************")
        print("***************************************************\n")

    for dirpath, _, filenames in os.walk(static):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dirpath, filename))

            if any(include_string in file_path.lower() for include_string in DONT_COMPRESS_PATHS):
                if file_path.endswith(".min.js") or file_path.endswith(".min.css"):

                    if verbose:
                        print(" " + file_path)

                    __hash_file(file_path, file_path, INTEIGRY_DICT, verbose)

    #
    # Creating HARD STATIC pages
    #

    if GIT_VERSIONING:

        if verbose:
            print("\n************ Static Files ************")
            print("**************************************\n")

        for dirpath, _, filenames in os.walk(TEMPLATES_PATH):
            for filename in filenames:

                file_path = os.path.abspath(os.path.join(dirpath, filename))

                if not any(include_string in file_path.lower() for include_string in
                           IGNORED_INCLUDE_STRINGS + DONT_COMPRESS_PATHS) and file_path.endswith(".comp.html"):

                    with open(file_path, "r") as f:
                        template = f.read()

                    template = template.replace("{{git_versioning}}", str(_VERSIONING_VALUE))
                    template = template.replace("<!DOCTYPE html>",
                                                "<!DOCTYPE html>\n\n<!-- File dynamically generated -->\n")

                    for key, value in INTEIGRY_DICT.items():
                        template = template.replace("{{" + key + ".integrity}}", value.integrity)
                        template = template.replace("{{" + key + ".static}}", value.static)

                    system_file_name = file_path.replace(".comp.html", ".html")

                    with open(system_file_name, "w") as f:
                        f.write(template)

                    if verbose:
                        print(" " + system_file_name)

    #
    # Create the integrity file
    #

    if MD5_VERSIONING:
        data = INTEGRITY_TEMPLATE.format("None", "{}")

    elif GIT_VERSIONING:
        value = "'{}'".format(_VERSIONING_VALUE)
        data = INTEGRITY_TEMPLATE.format(value, "{}")
    else:
        data = INTEGRITY_TEMPLATE.format("None", "{}")

    for key in sorted(INTEIGRY_DICT.keys()):
        value = INTEIGRY_DICT[key]

        data += "_INTEGRITY_DICT['{}']=StaticFile('{}','{}')\n".format(key, value.sha384, value.static)

    with open(INTEGRITY_FILE, "w") as f:
        f.write(data)

    sys.path.insert(2, os.path.dirname(INTEGRITY_FILE))

    from integrity import _INTEGRITY_DICT  # test of the file

    #
    # Git Revision
    #

    if verbose:
        print("\n************ Extra Data ************")
        print("**************************************\n")

    print()
    if GIT_VERSIONING and verbose:
        print(" Git Hash:\t{}".format(_VERSIONING_VALUE))

    if verbose:
        print(" Integrity.py:\t{} values".format(len(_INTEGRITY_DICT.values())))

    print()
    print()


if __name__ == "__main__":
    compress_directory(minify=False, reduce=True)
