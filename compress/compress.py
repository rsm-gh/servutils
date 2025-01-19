#!/usr/bin/python3

#
#  Copyright (C) Rafael Senties Martinelli. All Rights Reserved.
#

import re
import os
import sys
import hashlib
import subprocess
from typing import Literal
from base64 import b64encode
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compress.external.jsmin import jsmin
from compress.external.cssmin import cssmin
from compress.reduce_js import reduce_js

__version__ = "25.01.19"

class CompressConstants:
    _file_extension = ".comp"
    _info_tag = "@GENERATION_INFO"  # to be avoided if using the HTML5 integrity value (because of the datetime-hour)
    _include_js = "includeJS:"
    _include_css = "includeCSS:"
    _include = "include:"
    _static_path = "STATIC_PATH/" # the slash is important
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
                       integrity_dir: None | str,
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
Compressing static files (v{__version__}): 
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
    if integrity_dir is not None:
        __create_integrity_file(integrity_file=os.path.join(integrity_dir, "integrity.py"),
                                git_short_hash=git_short_hash,
                                verbose=verbose,
                                integrity_dict=integrity_dict)

def __get_git_revision_short_hash():
    return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()

def __path_from_line(line, tag, static_dir):

    path = line.split(tag, 1)[1].strip()

    if path.startswith(CompressConstants._static_path):
        complement = path.split(CompressConstants._static_path, 1)[1]
        path = os.path.join(static_dir, complement)

    return path

def __test_include_path(comp_path, include_path):
    if not os.path.exists(include_path):
        print(f"\nCritical Error: Non-Existent path '{include_path}' defined in '{comp_path}'")
        sys.exit(1)

# static_dir: str,
#                      git_short_hash: str,
#                      integrity_key_removal: str,
#                      verbose: bool,
#                      minify: bool,
#                      reduce: bool,
#                      versioning: None | str,
#                      ignore_paths: list[str]

def __get_comp_data(comp_path: str,
                    static_dir: str,
                    verbose: bool,
                    minify: bool,
                    reduce: bool) -> (str, bool, list):

    if verbose:
        print(" " + comp_path)

    with open(comp_path, "r") as f:
        template_lines = f.readlines()

    compressed_lines = []

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

            include_path = __path_from_line(line, CompressConstants._include_js, static_dir)
            __test_include_path(comp_path, include_path)

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

            include_path = __path_from_line(line, CompressConstants._include_css, static_dir)
            __test_include_path(comp_path, include_path)

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

            include_path = __path_from_line(line, CompressConstants._include, static_dir)
            __test_include_path(comp_path, include_path)

            with open(include_path, 'r') as f:
                read_lines = f.readlines()

            for read_line in read_lines:
                compressed_lines.append(read_line)

        else:
            compressed_lines.append(line)

    file_data = "\n".join(compressed_lines)

    return file_data, reduce_public_js, reduce_public_js_except


def __get_file_hash(abs_path: str) -> str:

    with open(abs_path, 'rb') as f:
        file_data = f.read()

    sha_digest = hashlib.sha384(file_data).digest()
    return b64encode(sha_digest).decode("utf-8")

def __add_to_integrity(system_path: str,
                       file_hash: str,
                       compressed_file: str,
                       integrity_key_removal: str,
                       dictionary: {},
                       verbose:bool):

    integrity_key = compressed_file.replace(integrity_key_removal, "", 1).lower()
    for forbidden_char, replace_char in (("/", "_"), ("-","_"), (".", "_")):
        integrity_key = integrity_key.replace(forbidden_char, replace_char)

    static_f = "/static/" + system_path.split("static/")[1]

    if verbose:
        print(f"\tkey:\t\t{integrity_key}")
        print(f"\tstatic:\t\t{static_f}")
        print(f"\tsha384:\t\t{file_hash}")
        print(f"\tf.name:\t\t{os.path.basename(system_path)}")
        print()

    static_file = StaticFile(file_hash, static_f)
    dictionary[integrity_key] = static_file


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


    #
    # Get the files and sort them
    #
    comp_paths = []
    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:

            abs_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in abs_path.lower() for include_string in ignore_paths) or not abs_path.endswith(
                    CompressConstants._file_extension):
                continue

            comp_paths.append(abs_path)

    comp_paths.sort()

    #
    # Process the comp paths
    #
    for comp_path in comp_paths:

        #
        # Get the content of the file
        #
        file_data, reduce_public_js, reduce_public_js_except = __get_comp_data(comp_path,
                                                                                static_dir,
                                                                                verbose,
                                                                                minify,
                                                                                reduce)

        #
        # Improve the indentation
        #
        file_data = file_data.replace("\t", "    ")  # this will normalize the spaces and place them into the end?
        while "    " in file_data:
            file_data = file_data.replace("    ", "\t")


        #
        # Define the system file name (can be renamed later)
        #
        system_path = comp_path.rsplit(CompressConstants._file_extension, 1)[0]
        integrity_key_path = system_path

        #
        # Reduce (encode) the data
        #

        encode_dictionary = ""
        if reduce and system_path.endswith(".js"):
            file_data, encode_dictionary = reduce_js(file_data,
                                                     public=reduce_public_js,
                                                     skip_items=reduce_public_js_except,
                                                     verbose=verbose)

        #
        # Write the file
        #
        with open(system_path, "w") as f:
            f.write(file_data)

        #
        # Calculate the hash
        #
        file_hash = __get_file_hash(system_path)

        #
        # Rename the file
        #

        if versioning in ("md5", "git"):

            if versioning == "md5":
                file_name = os.path.basename(system_path)

                if ".min." not in file_name:
                    raise ValueError(
                        'Error, invalid filename: It must end with ".js{0}" or ".css{0}" not filename = '.format(
                            CompressConstants._file_extension) + file_name)

                extension = file_name.rsplit(".", 1)[1]

                simplified_hash = file_hash.replace("/", "-")
                new_system_path = f"{os.path.dirname(system_path)}/.{simplified_hash}.min.{extension}"

            else:
                new_system_path = system_path.replace(".min.", f".{git_short_hash}.min.")

            os.rename(system_path, new_system_path)
            system_path = new_system_path


        #
        # Write the encode dictionary
        #
        if reduce and system_path.endswith(".js"):
            with open(system_path.replace("min.js", "min.dict"), "w") as f:
                f.write(encode_dictionary)


        #
        # Add to the integrity dict
        #
        __add_to_integrity(system_path=system_path,
                            file_hash=file_hash,
                            compressed_file=integrity_key_path,
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

    #
    # Get the file paths and sort them
    #
    file_paths = []
    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:
            file_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in file_path.lower() for include_string in dont_compress_paths):
                if file_path.endswith(".min.js") or file_path.endswith(".min.css"):

                    file_paths.append(file_path)

    file_paths.sort()

    #
    # Process the files
    #
    for file_path in file_paths:

        if verbose:
            print(" " + file_path)

        file_hash = __get_file_hash(file_path)

        __add_to_integrity(system_path=file_path,
                           file_hash=file_hash,
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

            if any(include_string in file_path.lower() for include_string in dont_compress_paths) or not file_path.endswith(CompressConstants._file_extension+".html"):
                continue

            with open(file_path, "r") as f:
                template = f.read()

            template = template.replace("{{git_versioning}}", git_short_hash)
            template = template.replace("<!DOCTYPE html>",
                                        "<!DOCTYPE html>\n\n<!-- File dynamically generated -->\n")

            for key, value in integrity_dict.items():
                template = template.replace("{{" + key + ".integrity}}", value.integrity)
                template = template.replace("{{" + key + ".static}}", value.static)

            system_path = file_path.replace(CompressConstants._file_extension+".html", ".html")

            with open(system_path, "w") as f:
                f.write(template)

            if verbose:
                print(" " + system_path)


def __create_integrity_file(integrity_file: str,
                            git_short_hash: str,
                            verbose: bool,
                            integrity_dict:dict) -> None:
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
