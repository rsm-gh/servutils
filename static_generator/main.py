#!/usr/bin/python3

#
# Copyright (c) 2021-2025 Rafael Senties Martinelli.
#
# Licensed under the Privative-Friendly Source-Shared License (PFSSL) v1.0.
# You may use, modify, and distribute this file under the terms of that license.
#
# This software is provided "as is", without warranty of any kind.
# The authors are not liable for any damages arising from its use.
#
# See the LICENSE file for more details.

# Todo: Option to update (and load) the exported map from an existent file
# Todo: Use md5 for the filenames ?
# Todo: rename arg as encode_js
# Todo: specify the files to replace (.html, .txt, etc..)

import re
import os
import sys
import json
import shutil
import hashlib
import subprocess
from typing import Literal
from base64 import b64encode
from datetime import datetime

from jsmin import jsmin
from cssmin import cssmin

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from static_generator.JSEncoder.main import reduce_js

__version__ = "25.06.21.1"

class CompressConstants:
    _file_extension = ".comp"
    _info_tag = "@GENERATION_INFO"  # to be avoided if using the HTML5 integrity value (because of the datetime-hour)
    _include_js = "includeJS:"
    _include_css = "includeCSS:"
    _include = "include:"
    _static_path = "STATIC_PATH/" # the slash is important
    _reduce_public_js_except = "reducePublicJSExcept:"

def run(static_dir: str,
                       templates_dir: str,
                       generation_dir: str,
                       map_file_name: None | str,
                       integrity_key_removal: str,
                       exclude_paths: None | list[str],
                       minify: bool = True,
                       reduce: bool = True,
                       versioning: None | Literal["md5", "git"] = "md5",
                       verbose: bool = True,
                       header_js: str = "",
                       header_css: str = "",
                       inline: bool = True,
                       clean: bool = True,
                       keep_tree: bool = False):
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

    print(f"""\n[CONFIGURATION]

version={__version__}: 
minify={minify}
reduce={reduce}
versioning={versioning}
verbose={verbose}
exclude_paths={exclude_paths}
static_dir={static_dir}
templates_dir={templates_dir}
map_file_name={map_file_name}
integrity_key_removal={integrity_key_removal}
inline="{inline}"
keep_tree={keep_tree}
generation_dir={generation_dir}
header_css={header_css}
header_js={header_js}""")

    if not os.path.exists(generation_dir):
        raise ValueError("The generation directory does not exist")

    if versioning not in (None, "md5", "git"):
        raise ValueError("Error: the only values that can be accepted for versioning are: None, 'md5' or 'git'.")

    if versioning == "git":
        git_short_hash = __get_git_revision_short_hash()
    else:
        git_short_hash = None

    if exclude_paths is None:
        exclude_paths = []


    if clean:
        print("\n[CLEANING GENERATION DIRECTORY]\n")
        if os.path.exists(generation_dir):
            shutil.rmtree(generation_dir)
            os.mkdir(generation_dir)


    #
    # Integrity dict
    #
    map_dict = {}

    #
    # Excluded files
    #
    __add_already_minified_files(static_dir=static_dir,
                                 integrity_key_removal=integrity_key_removal,
                                 verbose=verbose,
                                 exclude_paths=exclude_paths,
                                 map_dict=map_dict)

    #
    # Compressing the files
    #
    __compress_files(static_dir=static_dir,
                     generation_dir=generation_dir,
                     map_dict=map_dict,
                     git_short_hash=git_short_hash,
                     integrity_key_removal=integrity_key_removal,
                     verbose=verbose,
                     minify=minify,
                     reduce=reduce,
                     versioning=versioning,
                     exclude_paths=exclude_paths,
                     header_js = header_js,
                     header_css = header_css,
                     inline = inline)


    #
    # Creating HARD STATIC pages
    #
    __update_static_files(templates_dir=templates_dir,
                          generation_dir=generation_dir,
                          git_short_hash=git_short_hash,
                          exclude_paths=exclude_paths,
                          verbose=verbose,
                          map_dict=map_dict,
                          keep_tree=keep_tree)


    #
    # Create the integrity file
    #
    if map_file_name is not None:

        map_path = os.path.join(generation_dir, map_file_name)
        with open(map_path, "w") as f:
            f.write(json.dumps(map_dict, sort_keys=True, indent=4))

        print("Generated MAP file:", map_path)

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

def __get_comp_data(comp_path: str,
                    static_dir: str,
                    verbose: bool,
                    minify: bool,
                    reduce: bool,
                    inline: bool) -> (str, bool, list):

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

            if inline and not compressed_data.endswith(";"):
                compressed_data += ";"

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

            if inline and line.strip() == "":
                continue

            compressed_lines.append(line)

    if inline:
        file_data = "".join(compressed_lines)
    else:
        file_data = "\n".join(compressed_lines)

    return file_data, reduce_public_js, reduce_public_js_except


def __get_file_hash(abs_path: str) -> str:

    with open(abs_path, 'rb') as f:
        file_data = f.read()

    sha_digest = hashlib.sha384(file_data).digest()
    return b64encode(sha_digest).decode("utf-8")

def __add_map_entry(system_path: str,
                    static_path: str,
                    file_hash: str,
                    compressed_file: str,
                    integrity_key_removal: str,
                    dictionary: {},
                    verbose:bool):

    integrity_key = compressed_file.replace(integrity_key_removal, "", 1).lower()
    for forbidden_char, replace_char in (("/", "_"), ("-","_"), (".", "_")):
        integrity_key = integrity_key.replace(forbidden_char, replace_char)

    if verbose:
        print(f"\tkey:\t\t{integrity_key}")
        print(f"\tstatic:\t\t{static_path}")
        print(f"\tsha384:\t\t{file_hash}")
        print(f"\tf.name:\t\t{os.path.basename(system_path)}")
        print()

    dictionary[integrity_key] = {
        'abs_path': system_path,
        'integrity': "sha384-" + file_hash,
        'static': static_path,
    }


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


def __compress_files(static_dir: str,
                     generation_dir: str,
                     map_dict: {},
                     git_short_hash: str,
                     integrity_key_removal: str,
                     verbose: bool,
                     minify: bool,
                     reduce: bool,
                     versioning: None | str,
                     exclude_paths: list[str],
                     header_js: str = "",
                     header_css: str = "",
                     inline: bool = True) -> None:

    if verbose:
        print("\n[GENERATING JS & CSS FILES]\n")


    #
    # Get the files and sort them
    #
    comp_paths = []
    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:

            abs_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in abs_path for include_string in exclude_paths) or \
               not abs_path.endswith(CompressConstants._file_extension):
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
                                                                                reduce,
                                                                                inline)

        #
        # Improve the indentation
        #
        file_data = file_data.replace("\t", "    ")  # this will normalize the spaces and place them into the end?
        while "    " in file_data:
            file_data = file_data.replace("    ", "\t")


        #
        # Define the system file name (can be renamed later)
        #
        write_path = comp_path.rsplit(CompressConstants._file_extension, 1)[0] # Remove the extension
        integrity_key_path = write_path
        write_path = os.path.join(os.path.join(static_dir, generation_dir), os.path.basename(write_path))

        #
        # Reduce (encode) the data
        #
        encode_dictionary = ""
        if reduce and write_path.endswith(".js"):
            file_data, encode_dictionary = reduce_js(file_data,
                                                     public=reduce_public_js,
                                                     skip_items=reduce_public_js_except,
                                                     verbose=verbose)

        #
        # Add the header
        #
        if write_path.endswith(".css"):
            file_data = header_css + file_data

        elif write_path.endswith(".js"):
            file_data = header_js + file_data

        #
        # Write the file
        #
        with open(write_path, "w") as f:
            f.write(file_data)

        #
        # Calculate the hash
        #
        file_hash = __get_file_hash(write_path)

        #
        # Rename the file
        #

        if versioning in ("md5", "git"):

            file_name = os.path.basename(write_path)

            if ".min." not in file_name:
                raise ValueError(
                    'Error, invalid filename: It must end with ".js{0}" or ".css{0}" not filename = '.format(
                        CompressConstants._file_extension) + file_name)

            if versioning == "md5":
                new_value = file_hash
            else:
                new_value = git_short_hash


            new_value = new_value.replace("/", "-") # Any slash would break the system path
            file_extension = file_name.rsplit(".min.", 1)[1]
            new_file_name = f"{new_value}.min.{file_extension}"
            new_write_path = os.path.join(os.path.dirname(write_path), new_file_name)
            os.rename(write_path, new_write_path)
            write_path = new_write_path


        #
        # Write the encode dictionary
        #
        if reduce and write_path.endswith(".js"):
            with open(write_path.replace("min.js", "min.dict"), "w") as f:
                f.write(encode_dictionary)


        #
        # Add to the integrity dict
        #
        if map_dict is not None:
            static_path = f"/{os.path.basename(generation_dir)}{write_path.replace(generation_dir, "")}"
            __add_map_entry(system_path=write_path,
                           static_path=static_path,
                           file_hash=file_hash,
                           compressed_file=integrity_key_path,
                           integrity_key_removal=integrity_key_removal,
                           dictionary=map_dict,
                           verbose=verbose)


def __add_already_minified_files(static_dir: str,
                                 integrity_key_removal: str,
                                 verbose: bool,
                                 exclude_paths: list[str],
                                 map_dict: {}) -> dict:

    if verbose:
        print("\n[ADDING ALREADY MINIFIED FILES]\n")

    #
    # Get the file paths and sort them
    #
    file_paths = []
    for dir_path, _, filenames in os.walk(static_dir):
        for filename in filenames:
            file_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in file_path for include_string in exclude_paths):
                continue

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
        static_path = "/static/" + file_path.split("static/")[1]

        __add_map_entry(system_path=file_path,
                       static_path=static_path,
                       file_hash=file_hash,
                       compressed_file=file_path,
                       integrity_key_removal=integrity_key_removal,
                       dictionary=map_dict,
                       verbose=verbose)

    return map_dict # this may not be necessary, but it will clarify the output.

def __update_static_files(templates_dir: str,
                          generation_dir: str,
                          git_short_hash: str | None,
                          exclude_paths: list[str],
                          verbose: bool,
                          map_dict: dict,
                          keep_tree: bool = False) -> None:

    if verbose:
        print("\n[GENERATING STATIC FILES]\n")

    for dir_path, _, filenames in os.walk(templates_dir):
        for filename in filenames:

            template_path = os.path.abspath(os.path.join(dir_path, filename))

            if any(include_string in template_path for include_string in exclude_paths):
                continue

            if not template_path.endswith(CompressConstants._file_extension+".html"):
                continue

            with open(template_path, "r") as f:
                template = f.read()

            if git_short_hash is not None:
                template = template.replace("{{git_versioning}}", git_short_hash)

            template = template.replace("<!DOCTYPE html>",
                                        "<!DOCTYPE html>\n\n<!-- File dynamically generated -->\n")

            for key, values in map_dict.items():

                integrity = values['integrity']
                static = values['static']

                template = template.replace("{{" + key + ".integrity}}", integrity)
                template = template.replace("{{" + key + ".static}}", static)


            final_name = os.path.basename(template_path).replace(".comp.",".")

            if keep_tree:

                if not templates_dir.endswith("/"):
                    templates_dir += "/"

                base_name = os.path.basename(os.path.dirname(templates_dir))
                rel_path = template_path.split(templates_dir)[1]
                write_dir =  os.path.dirname(os.path.join(generation_dir, base_name, rel_path))

                if not os.path.exists(write_dir):
                    os.makedirs(write_dir)

                write_path = os.path.join(write_dir, final_name)

            else:
                write_path = os.path.join(generation_dir, final_name)

            if os.path.exists(write_path):
                raise ValueError("File already exists: " + write_path)

            with open(write_path, "w") as f:
                f.write(template)

            if verbose:
                print(" " + write_path)