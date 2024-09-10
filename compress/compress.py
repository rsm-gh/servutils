#!/usr/bin/python3

#
#  Copyright (C) 2021-2024 Rafael Senties Martinelli. All Rights Reserved.
#

import re
import os
import sys
import subprocess
from typing import Literal
from base64 import b64encode
from datetime import datetime
from hashlib import sha384, md5

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compress.external.jsmin import jsmin
from compress.external.cssmin import cssmin
from compress.reduce_js import reduce_js

class CompressConstants:
    _info_tag = "@GENERATION_INFO"  # to be avoided if using the HTML5 integrity value (because of the datetime-hour)
    _include_js = "includeJS:"
    _include_css = "includeCSS:"
    _include = "include:"
    _reduce_public_js_except = "reducePublicJSExcept:"
    _integrity_template = """#!/usr/bin/python3

# This file is dynamically generated, DO NOT MODIFY IT by hand.

class StaticFile:
    def __init__(self, file_sha384: str , static_path: str) -> None:
        # The attributes can not be protected, or django template will not be able to read them.
        self.sha384 = file_sha384
        self.integrity = "sha384-" + file_sha384
        self.static = static_path

_GIT_SHORT_HASH = {}
_INTEGRITY_DICT = {}
"""

class StaticFile:
    def __init__(self, file_sha384: str , static_path: str) -> None:
        # The attributes can not be protected, or django template will not be able to read them.
        self.sha384 = file_sha384
        self.integrity = "sha384-" + file_sha384
        self.static = static_path


def compress_directory(static_dir: str,
                       templates_dir: str,
                       integrity_dir: str,
                       integrity_key_removal: str,
                       exclude_paths: None | list[str],
                       dont_compress_paths: None | list[str],
                       minify: bool = True,
                       reduce: bool = True,
                       versioning: None | Literal["md5", "git"] = "md5",
                       verbose: bool = True):
    """
        versioning:
            In order to always update the JS & CSS, it is important to add a version
            system in their file name. That forces the browser to reload the content
            in case of changes.

            md5: will use the md5 of the file content as file name. This is the best
                 options since it will only force a reload when the content changes.

            git: will include the short hash in the file name. The  problem  with
                 this option, is that any commit, will force the reload of ALL the
                 JS & CSS files.

            None: will use the original file name.
    """


    print(f"""
Compressing static files: 
    minify={minify}
    reduce={reduce}
    versioning={versioning}
    verbose={verbose}
    exclude_paths={exclude_paths}
    dont_compress_paths={dont_compress_paths}
    static_dir={static_dir}
    templates_dir={templates_dir}
    integrity_dir={integrity_dir}
    integrity_key_removal={integrity_key_removal}
""")

    if versioning not in (None, "md5", "git"):
        raise ValueError("Error: the only values that can be accepted for versioning are: None, 'md5' or 'git'.")

    integrity_file = os.path.join(integrity_dir, "integrity.py")

    git_short_hash = __get_git_revision_short_hash()

    if exclude_paths is None:
        exclude_paths = []

    ignore_paths = exclude_paths + dont_compress_paths

    #
    # Delete old files
    #
    __remove_old_files(static_dir, verbose, ignore_paths)

    #
    # Compressing the files
    #
    integrity_dict = __compress_files(static_dir=static_dir,
                                     git_short_hash=git_short_hash,
                                     integrity_key_removal=integrity_key_removal,
                                     verbose=verbose,
                                     minify=minify,
                                     reduce=reduce,
                                     versioning=versioning,
                                     ignore_paths=ignore_paths)

    #
    # Excluded files
    #
    integrity_dict = __add_excluded_files(static_dir=static_dir,
                                            dont_compress_paths=dont_compress_paths,
                                            integrity_key_removal=integrity_key_removal,
                                            verbose=verbose,
                                            integrity_dict=integrity_dict)


    #
    # Creating HARD STATIC pages
    #
    __create_static_pages(templates_dir=templates_dir,
                          git_short_hash=git_short_hash,
                          dont_compress_paths=dont_compress_paths,
                          verbose=verbose,
                          integrity_dict=integrity_dict)


    #
    # Create the integrity file
    #
    file_dict = __create_integrity_file(integrity_file=integrity_file,
                                        git_short_hash=git_short_hash,
                                        verbose=verbose,
                                        integrity_dict=integrity_dict)

def __get_git_revision_short_hash():
    return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()

def __path_from_path(line, tag):
    return line.split(tag, 1)[1].strip()

def __hash_file(system_file_name: str,
                compressed_file: str,
                integrity_key_removal: str,
                dictionary: {},
                verbose:bool):
    with open(system_file_name, 'rb') as f:
        file_sha384 = b64encode(sha384(f.read()).digest()).decode("utf-8")

    integrity_key = compressed_file.replace(integrity_key_removal, "", 1).replace("/", "_").replace("-","_").replace(".", "_").lower()

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

def __remove_old_files(static_dir: str,
                       verbose:bool,
                       ignore_paths: list[str]) -> None:

    if verbose:
        print("\n************ Deleting ************")
        print("**********************************\n")

    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dir_path, filename))
            if not any(include_string in file_path.lower() for include_string in ignore_paths) and \
                    (file_path.endswith(".min.js") or file_path.endswith(".min.dict") or file_path.endswith(".min.css")):
                os.remove(file_path)

                if verbose:
                    print(" {}".format(file_path))


def __compress_files(static_dir: str,
                     git_short_hash: str,
                     integrity_key_removal: str,
                     verbose: bool,
                     minify: bool,
                     reduce: bool,
                     versioning: None | str,
                     ignore_paths: list[str]) -> dict:

    integrity_dict = {}

    if verbose:
        print("\n************ Compressing ************")
        print("*************************************\n")

    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in file_path.lower() for include_string in ignore_paths) or not file_path.endswith(".comp"):
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

                if CompressConstants._info_tag in line:
                    new_line = line.replace(CompressConstants._info_tag, "@Generated at: {}".format(datetime.now()))
                    compressed_lines.append(new_line)

                elif line.startswith(CompressConstants._reduce_public_js_except):

                    reduce_public_js = True

                    exclude_methods = line.split(CompressConstants._reduce_public_js_except, 1)[1]

                    for elem in exclude_methods.split(";"):

                        elem = elem.strip()

                        if elem != "":
                            reduce_public_js_except.append(elem)

                elif line.startswith(CompressConstants._include_js):

                    include_path = __path_from_path(line, CompressConstants._include_js)

                    with open(include_path, 'r') as f:
                        data = f"/* {CompressConstants._include_js}{include_path} */\n" + f.read()

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
                            print("\t" + c_line[:50])

                elif line.startswith(CompressConstants._include_css):

                    include_path = __path_from_path(line, CompressConstants._include_css)

                    with open(include_path, 'r') as f:
                        data = f"/* {CompressConstants._include_css}{include_path} */\n" + f.read()

                    if minify:
                        compressed_data = cssmin(data)
                    else:
                        compressed_data = data

                    # comp_css = cssmin(sys.stdin.read(), wrap=options.wrap)
                    compressed_data = compressed_data.replace("+", " + ").replace("  ", " ")
                    compressed_data = compressed_data.replace('opacity:0', 'opacity: 0')

                    compressed_lines.append(compressed_data)


                elif line.startswith(CompressConstants._include):

                    include_path = __path_from_path(line, CompressConstants._include)

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

            compressed_file = file_path.rsplit(".comp", 1)[0]

            if versioning == "md5":
                file_name = os.path.basename(compressed_file)

                if "." not in file_name:
                    raise ValueError(
                        'Error, invalid filename: It must end with ".js.comp" or ".css.comp" not filename = ' + file_name)

                extension = file_name.rsplit(".", 1)[1]

                md5_creator = md5()
                md5_creator.update(file_data.encode())

                system_file_name = "{}/{}.min.{}".format(os.path.dirname(compressed_file),
                                                            md5_creator.hexdigest(),
                                                            extension)

            elif versioning == "git":
                system_file_name = compressed_file.replace(".min.", ".{}.min.".format(git_short_hash))

            else:
                system_file_name = compressed_file

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

            __hash_file(system_file_name=system_file_name,
                        compressed_file=compressed_file,
                        integrity_key_removal=integrity_key_removal,
                        dictionary=integrity_dict,
                        verbose=verbose)

    return integrity_dict


def __add_excluded_files(static_dir: str,
                         integrity_key_removal: str,
                         verbose: bool,
                         dont_compress_paths: list[str],
                         integrity_dict:dict) -> dict:

    if verbose:
        print("\n************ Excluded from compression ************")
        print("***************************************************\n")

    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in file_path.lower() for include_string in dont_compress_paths):
                if file_path.endswith(".min.js") or file_path.endswith(".min.css"):

                    if verbose:
                        print(" " + file_path)

                    __hash_file(system_file_name=file_path,
                                compressed_file=file_path,
                                integrity_key_removal=integrity_key_removal,
                                dictionary=integrity_dict,
                                verbose=verbose)

    return integrity_dict # this may not be necessary, but it will clarify the output.

def __create_static_pages(templates_dir: str,
                          git_short_hash: str,
                          dont_compress_paths: list[str],
                          verbose: bool,
                          integrity_dict: dict) -> None:

    if verbose:
        print("\n************ Static Files ************")
        print("**************************************\n")

    for dir_path, _, filenames in os.walk(templates_dir):
        for filename in filenames:

            file_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in file_path.lower() for include_string in dont_compress_paths) or not file_path.endswith(".comp.html"):
                continue

            with open(file_path, "r") as f:
                template = f.read()

            template = template.replace("{{git_versioning}}", git_short_hash)
            template = template.replace("<!DOCTYPE html>",
                                        "<!DOCTYPE html>\n\n<!-- File dynamically generated -->\n")

            for key, value in integrity_dict.items():
                template = template.replace("{{" + key + ".integrity}}", value.integrity)
                template = template.replace("{{" + key + ".static}}", value.static)

            system_file_name = file_path.replace(".comp.html", ".html")

            with open(system_file_name, "w") as f:
                f.write(template)

            if verbose:
                print(" " + system_file_name)


def __create_integrity_file(integrity_file: str,
                            git_short_hash: str,
                            verbose: bool,
                            integrity_dict:dict) -> dict:
    integrity_data = ""
    for key in sorted(integrity_dict.keys()):
        value = integrity_dict[key]
        integrity_data += f"    '{key}':\n        StaticFile('{value.sha384}',\n                   '{value.static}'),\n"
    integrity_data = "{\n"+integrity_data+"}"

    integrity_template = CompressConstants._integrity_template.format(f"'{git_short_hash}'", integrity_data)
    with open(integrity_file, "w") as f:
        f.write(integrity_template)

    #
    # Test the file
    #
    sys.path.insert(2, os.path.dirname(integrity_file))
    from integrity import _INTEGRITY_DICT, _GIT_SHORT_HASH

    #
    # Git Revision
    #
    if verbose:
        print("\n************ integrity.py ************")
        print("**************************************\n")

    if verbose:
        print(" _GIT_SHORT_HASH:\t{}".format(_GIT_SHORT_HASH))
        print(" _INTEGRITY_DICT:\t{} values".format(len(_INTEGRITY_DICT.values())))

    print()
    print()


if __name__ == "__main__":
    compress_directory(static_dir="/home/cadweb/cadweb/core/static/",
                       templates_dir="/home/cadweb/cadweb/core/templates/",
                       integrity_dir="/home/cadweb/cadweb/core/django/cadweb/",
                       integrity_key_removal="/home/cadweb/cadweb/core/static/",
                       exclude_paths=[".git/"],
                       dont_compress_paths=["external/"],
                       minify=False,
                       reduce=True,
                       versioning=None)
