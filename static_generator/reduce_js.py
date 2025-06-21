#!/usr/bin/python3

#
# Copyright (c) 2022-2024 Rafael Senties Martinelli.
#
# Licensed under the Privative-Friendly Source-Shared License (PFSSL) v1.0.
# You may use, modify, and distribute this file under the terms of that license.
#
# This software is provided "as is", without warranty of any kind.
# The authors are not liable for any damages arising from its use.
#
# See the LICENSE file for more details.

"""
    + THE CODE MUST NOT HAVE COMMENTS OR THE REDUCE WILL NOT PROPERLY WORK.

    + Only "self" can be used as substitute for "this" on closure functions.
    + Avoid using dictionary keys with variables names, example:

        [{x: x}]

        because the key "x" will be replaced with the variable "x". A real case error arrived with:

        [{data: data}]  and was replaced with [{data: chart_data}]

    Advices:
        Avoid using 'list' item for accessing dictionaries: SESSION_DATA["ulogged"] instead SESSION_DATA.ulogged
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from static_generator.ReduceData import ReduceData

__FUNCTION_INDEX = 0  # some JS files my load other files, functions must not be overwritten
__CONSTANT_INDEX = 0  # some JS files my load other files, functions must not be overwritten
__CLASS_INDEX = 0  # some JS files my load other files, functions must not be overwritten

class ReduceSettings:
    _debug = False
    _min_var_replacement_len = 3  # var abc
    _single_line_comments = ('/"/g', "/'/g")  # JS chars with an un-finished comment character
    _exclude_public_method_names = ['constructor',
                                     'addEventListener',
                                     'display',
                                     'onclick',
                                     'onreadystatechange']
    _re_split_js = r'([\s\[\]\(\)\{\}\'\*\"\?\+\.\-:;,%/!&|=<>])'  # ([\s\[\](){}.:;,"\'*?%/!&|=+-<>])

def reduce_js(text, vars_on_functions=True, vars_on_methods=True, public=False, skip_items=None, verbose=True):
    """
        reduce the size of private methods
    """
    global __CONSTANT_INDEX, __FUNCTION_INDEX, __CLASS_INDEX

    if skip_items is None:
        skip_items = []

    reduce_data = ReduceData()

    initial_size = sys.getsizeof(text)

    #
    # Prepare the items to search
    #

    search_words = re.split(ReduceSettings._re_split_js, text)

    # Remove empty chars. Why they are empty chars?
    search_words = [char for char in search_words if not char == '']
    search_words = __join_text_comments(search_words)

    if ReduceSettings._debug:
        print(search_words)

    #
    # Replace the local variables in functions: var foo =
    #

    if vars_on_functions:
        search_words = __reduce_js_on_functions(search_words, reduce_data)

    #
    # Get all the methods
    #

    if vars_on_methods:
        # reduce vars
        search_words = __reduce_js_on_class(search_words, reduce_data)

        # reduce method names
        search_words = __reduce_js_on_class(search_words, reduce_data, True)

    #
    # Detect private constants and its content (if dictionary)
    # Also replace its initialization values
    #

    """    
        const __PDATA_STATUS = {
            created : 10,
            uploading : 20,
        };
    """

    current_constant = ""
    inside_dict_const = False
    dict_level_index = 0

    func_level = 0

    for i, word in enumerate(search_words):

        prev3_char, prev2_char, prev1_char = __get_previous_char(search_words, i, 3)

        if word.strip() == "":
            continue

        if word == "{":
            func_level += 1

        elif word == "}":
            func_level -= 1

        # Detect constants
        #
        if func_level == 0 and \
                prev1_char == "const" and \
                ((word.startswith("__") and word not in skip_items) or
                 (public and word.replace("_", "").isalnum())) and word not in skip_items:

            __CONSTANT_INDEX += 1
            constant_encode = "C" + str(__CONSTANT_INDEX)
            reduce_data.add_constant(word, constant_encode)

            current_constant = word
            word = constant_encode

        elif word == "{" and \
                prev1_char == "=" and \
                current_constant != "" and \
                prev2_char == current_constant and \
                prev3_char == "const":

            inside_dict_const = True

        if inside_dict_const:

            if word == "{":
                dict_level_index += 1

            elif word == "}":
                dict_level_index -= 1

            if dict_level_index <= 0:
                inside_dict_const = False
                current_constant = ""
                continue

            if word == ":":
                added, encode = reduce_data.add_constant_parameter(current_constant, prev1_char)

                if added:

                    replaced, search_words = __replace_previous_char(search_words, prev1_char, encode, i - 1)

                    if not replaced:
                        reduce_data.add_error(
                            "Error replacing constant definition parameter. {}.{}:{}".format(current_constant,
                                                                                             prev1_char, encode))

    # Replace private constants when used in the code
    #

    for constant_name in sorted(reduce_data.constants.keys()):

        constant_data = reduce_data.constants[constant_name]

        # Replace parameters
        if len(constant_data.parameters) > 0:

            #  __CONST.PARAMETER

            for i, word in enumerate(search_words):

                prev2_char, prev1_char = __get_previous_char(search_words, i, 2)

                if prev2_char == constant_name and prev1_char == ".":

                    try:
                        param_encode = constant_data.parameters[word]
                    except KeyError:
                        reduce_data.add_error("Parameter={} not found in constant={}".format(word, constant_name))
                        continue

                    search_words[i] = param_encode

        # Replace constant names
        for i, word in enumerate(search_words):
            if word == constant_name:
                search_words[i] = constant_data.encode

    #
    # Replace all the function names:  function __foo (){}
    #
    public_function_names = []

    for func_name in sorted(reduce_data.functions.keys()):

        if not func_name.startswith("__"):
            public_function_names.append(func_name)

            if not public or func_name in skip_items + ReduceSettings._exclude_public_method_names:
                continue

        func_data = reduce_data.functions[func_name]
        func_data.encode = "f" + str(__FUNCTION_INDEX)

        for i, word in enumerate(search_words):
            if word == func_name:
                search_words[i] = func_data.encode

        __FUNCTION_INDEX += 1

    #
    # Replace public method names
    #
    if public:

        public_method_names = {}

        # the methods with the same name across classes must be renamed equally. Ex:
        #
        # CadSocket.print() & CadViewer.print() --> CadSocket.mp1() & CadViewer.mp1()
        #
        for class_data in reduce_data.classes.values():
            for method_data in class_data.methods.values():

                method_name = method_data.name

                if not method_name.startswith("__") and \
                        method_name not in ReduceSettings._exclude_public_method_names and \
                        method_name not in public_method_names.keys() and \
                        method_name not in skip_items:
                    encode = "mp{}".format(len(public_method_names))
                    public_method_names[method_name] = encode
                    method_data.encode = encode

        for i, word in enumerate(search_words):

            prev1_char = __get_previous_char(search_words, i, 1)

            if word == "(" and prev1_char in public_method_names.keys():
                # replace at the definition:  method(){}

                if prev1_char in public_function_names:
                    reduce_data.add_error("Warning, public method name same as public function={}".format(prev1_char))
                    continue

                encode = public_method_names[prev1_char]

                replaced, search_words = __replace_previous_char(search_words, prev1_char, encode, i - 1)

                if not replaced:
                    reduce_data.add_error("Error replacing public method name. {}:{}".format(prev1_char, encode))




            elif prev1_char == "." and word in public_method_names.keys():
                # replace when accessed:  class_obj.method

                if word in public_function_names:
                    reduce_data.add_error("Warning, public method name same as public function={}".format(word))
                    continue

                encode = public_method_names[word]
                search_words[i] = encode

    # Replace class names
    if public:

        for class_name, class_data in reduce_data.classes.items():

            if class_name not in skip_items:

                __CLASS_INDEX += 1

                class_encode = "CL{}".format(__CLASS_INDEX)

                class_data.encode = class_encode

                for i, word in enumerate(search_words):

                    if word == class_name:
                        search_words[i] = class_encode

    # END
    #

    reduced_text = "".join(char for char in search_words)

    end_size = sys.getsizeof(reduced_text)

    if verbose:
        print("\treduced:\t{}%".format(round((1 - (end_size / initial_size)) * 100, 1)))

    if ReduceSettings._debug:
        print(reduce_data)

    if len(reduce_data.errors) > 0:
        for error in reduce_data.errors:
            print(error)

        exit(1)

    return reduced_text, str(reduce_data)


def __replace_previous_char(search_list, match_item, value, start):
    """
        This will find a string in a list and replace it.
        This function is used for replace values when the exact index may not be known. ExL
             __get_previous_char
            do not give an index, because it excludes spaces.
    """

    while start >= 0:
        if search_list[start] == match_item:
            search_list[start] = value
            return True, search_list
        else:
            start -= 1

    return False, search_list


def __get_previous_char(search_list, start, x=1):
    """
        return a list (or word if x=1) X places in the list excluding spaces
    """

    final_char = ""
    index = start  # -1 at the beginning of the loop
    chars = []

    while len(chars) < x:

        index -= 1

        try:
            previous_char = search_list[index]
        except IndexError:
            break

        if previous_char.strip() != "":
            chars.append(previous_char)
            final_char = previous_char

    if x == 1:
        return final_char
    else:
        chars.reverse()
        return chars


def __get_non_empty_next_chars(search_list, start, chars_nb):
    chars = []

    index = start

    while len(chars) < chars_nb:

        index += 1

        try:
            current_char = search_list[index]
        except IndexError:
            break

        if current_char.strip() != "":
            chars.append(current_char)

    return chars


def __reduce_function_block(function_words, func_name, reduce_data, class_name=None):
    """
        Rename the content inside a function or a method:
            + arguments
            + variables (const, let, var)

        inside functions are excluded.
    """
    global __FUNCTION_INDEX

    if class_name is None:
        if func_name.startswith("__"):
            __FUNCTION_INDEX += 1
            reduce_data.add_function(func_name, "f" + str(__FUNCTION_INDEX))
        else:
            reduce_data.add_function(func_name, None)

    #
    # Find the arguments
    #

    # Join the function header
    args_header = ""
    inside_args = False

    for char in function_words:
        if char == "(":
            inside_args = True
            continue

        if inside_args:

            if char == ")":
                break

            args_header += char

    for char in args_header.split(","):

        if "=" in char:
            arg_name = char.split("=")[0]
        else:
            arg_name = char

        arg_name = arg_name.strip()

        if arg_name != "" and arg_name != "self":
            if class_name is None:
                reduce_data.add_function_arg(func_name, arg_name)
            else:
                reduce_data.add_method_arg(class_name, func_name, arg_name)

    #
    # Fin the keywords: var, let, const
    #
    consts = []
    lets = []

    for i, char in enumerate(function_words):

        previous_char = __get_previous_char(function_words, i)

        if len(char.strip()) >= ReduceSettings._min_var_replacement_len:

            if previous_char == "var":
                if class_name is None:
                    reduce_data.add_function_var(func_name, char)
                else:
                    reduce_data.add_method_var(class_name, func_name, char)

            elif previous_char == "const" and char not in consts:

                if class_name is None:
                    reduce_data.add_function_const(func_name, char)
                else:
                    reduce_data.add_method_const(class_name, func_name, char)

            elif previous_char == "let" and char not in lets:

                if class_name is None:
                    reduce_data.add_function_let(func_name, char)
                else:
                    reduce_data.add_method_let(class_name, func_name, char)

    #
    # Replace the data
    #

    if class_name is None:
        arguments = reduce_data.get_function_args(func_name)
        variables = reduce_data.get_function_vars(func_name)
        constants = reduce_data.get_function_constants(func_name)
        lets = reduce_data.get_function_lets(func_name)
    else:
        arguments = reduce_data.get_method_args(class_name, func_name)
        variables = reduce_data.get_method_vars(class_name, func_name)
        constants = reduce_data.get_method_constants(class_name, func_name)
        lets = reduce_data.get_method_lets(class_name, func_name)

    for replace_list in (arguments, variables, constants, lets):

        for arg_name, arg_encode in replace_list.items():

            for j, char in enumerate(function_words):

                previous_char = __get_previous_char(function_words, j)

                if char == arg_name and not previous_char == ".":  # previous_char == ".", is a property
                    function_words[j] = arg_encode

    # Debug INFO
    #

    if ReduceSettings._debug:
        print(function_words)

    return function_words


def __reduce_js_on_class(search_words, reduce_data, replace_method_names=False):
    """
        Iterate to find classes, then find methods inside classes and do the work:

            Either:
                + Reduce the arguments and the variables inside methods.
                + FIll the reduce_data file
            or:
                + Replace the private method names.
    """

    new_words = []
    method_words = []

    class_tag = False
    class_accolade_levels = -1
    possible_class_name = ""

    replace_methods = {}
    replace_properties = {}

    inside_method = False
    method_accolade_levels = -1
    possible_method_name = ""
    current_sequence = ""

    for i, word in enumerate(search_words):

        if word == "class" and class_tag is False:
            class_tag = True
            class_accolade_levels = -1
            possible_class_name = ""

            inside_method = False
            method_accolade_levels = 0
            current_sequence = ""
            possible_method_name = ""

            new_words.append(word)
            continue

        #
        # Exit if we do not suspect to be inside a class
        #
        if not class_tag:
            new_words.append(word)
            continue

        #
        # Continue searching for a class
        #
        if possible_class_name == "":

            if word.strip() == "":
                pass
            elif not word.isalnum():
                class_tag = False
            else:
                possible_class_name = word

            new_words.append(word)
            continue

        # this is to remove comments containing the word class
        if not word.strip() in ("{", "") and class_accolade_levels == -1:
            class_tag = False
            possible_class_name = ""

            new_words.append(word)
            continue

        if word == "{":
            if class_accolade_levels == -1:

                if ReduceSettings._debug:
                    print("\nCLASS FOUND: " + possible_class_name)

                if not replace_method_names:
                    reduce_data.add_class(possible_class_name)

                    replace_methods = {}
                    replace_properties = {}

                else:
                    replace_methods = reduce_data.get_replace_method_names(possible_class_name)
                    replace_properties = reduce_data.get_replace_properties(possible_class_name)

                class_accolade_levels = 1
            else:
                class_accolade_levels += 1


        elif word == "}":
            class_accolade_levels -= 1

            if class_accolade_levels <= 0:

                class_accolade_levels = -1
                class_tag = False
                possible_class_name = ""

                replace_methods = {}
                replace_properties = {}

                if ReduceSettings._debug:
                    print(" EXIT CLASS")

        #
        # IF WE ARE INSIDE A CLASS, THEN:
        #

        if replace_method_names:

            if word.startswith("__"):

                if word in replace_methods.keys():
                    # Replace method names
                    #
                    search_words[i] = replace_methods[word]

                elif word in replace_properties.keys():
                    # Replace method properties
                    #
                    previous_chars = __get_previous_char(search_words, i, 2)

                    if len(previous_chars) == 2:

                        if previous_chars[0] in ('this', 'self') and \
                                previous_chars[1] == ".":
                            search_words[i] = replace_properties[word]

            continue  # exit the loop

        #
        # Find properties, even if they are outside a method.
        #

        if word in ("self", "this"):  # this.prop = "toto"
            next_chars = __get_non_empty_next_chars(search_words, i, 3)

            if len(next_chars) == 3 and \
                    next_chars[0] == "." and \
                    next_chars[2] == "=" and \
                    next_chars[1].startswith("__"):
                reduce_data.add_property(possible_class_name, next_chars[1])

        #
        # IF Reduce inside methods
        #

        # Start to detect the method

        if not word.strip() in ("", "(") and current_sequence == "":
            possible_method_name = word

        if word in ("(", ")", "{") and inside_method is False:

            if word == "{" and ")" not in current_sequence:

                # this is to remove dictionaries when
                #
                # method(test={}){
                #
                # }
                #
                pass

            else:
                current_sequence += word

            if current_sequence not in ("(", "()", "(){"):
                current_sequence = ""
                new_words.append(word)
                continue

            elif current_sequence == "(){":
                inside_method = True
                method_accolade_levels = 0
                method_words = []

                # append the previous data: foo (arg1, args){
                for j, char in enumerate(reversed(new_words)):
                    if char == possible_method_name:
                        method_words += new_words[-(j + 1):]
                        new_words = new_words[:-(j + 1)]
                        break

                if ReduceSettings._debug:
                    print(possible_class_name + "." + possible_method_name)

                reduce_data.add_method(possible_class_name, possible_method_name)

        # Method exit
        if not inside_method:
            new_words.append(word)
            continue

        method_words.append(word)

        if word == "{":
            method_accolade_levels += 1

        elif word == "}":
            method_accolade_levels -= 1

            if method_accolade_levels <= 0:
                method_accolade_levels = 0
                current_sequence = ""
                inside_method = False

                function_block = __reduce_function_block(method_words, possible_method_name, reduce_data,
                                                         possible_class_name)

                if ReduceSettings._debug:
                    function_block = ["\n\n// METHOD //\n"] + function_block + ["\n// END METHOD //\n\n"]

                new_words += function_block

    if replace_method_names:
        new_words = search_words

    return new_words


def __reduce_js_on_functions(search_words, reduce_data):
    function_block = []
    new_words = []
    bracket_level = 0
    inside_function = False

    for i, char in enumerate(search_words):

        if char == "function" and inside_function is False:

            # function foo (
            # exclude:
            # toto = function(){}

            previous_char = __get_previous_char(search_words, i)

            if previous_char != "=":  # to exclude functions inside functions or methods

                chars = __get_non_empty_next_chars(search_words, i, 2)

                if len(chars) == 2 and chars[0].replace("_", "").isalnum() and chars[1] == "(":
                    function_name = chars[0]
                    inside_function = True
                    bracket_open = False
                    function_block = [char]

            if not inside_function:
                function_name = ""
                new_words.append(char)


        elif inside_function:

            if bracket_open:
                pass
            elif "{" in char:
                bracket_open = True

            bracket_level += char.count("{")
            bracket_level -= char.count("}")
            function_block.append(char)

            if bracket_level <= 0 and bracket_open:

                function_block = __reduce_function_block(function_block, function_name, reduce_data)

                if ReduceSettings._debug:
                    function_block = ["\n\n// FUNCTION //\n"] + function_block + ["\n// END FUNCTION //\n\n"]

                new_words += function_block

                inside_function = False
                bracket_level = 0
                function_block = []



        else:
            new_words.append(char)

    return new_words


def __join_text_comments(search_words):
    """
       Join the comments into a single word. This avoids bugs with the "-" sign
       when it is used inside JS for defining classes ex "window-big"
    """

    #
    # Join single line comments like regex patterns:  /'/g
    #

    for single_comment in ReduceSettings._single_line_comments:

        comment_list = list(single_comment)
        comment_length = len(comment_list)

        new_words = []

        debug_index = []

        i = 0
        while i < len(search_words):

            # print(i, "---", search_words[i])

            try:
                chars = search_words[i:i + comment_length]
            except IndexError:
                chars = []

            if chars == comment_list:
                new_words.append(single_comment)
                debug_index.append(len(new_words))
                i += comment_length

            else:
                new_words.append(search_words[i])

                i += 1

        search_words = new_words

    #
    #

    new_words = []
    buffer = []
    delimiter = None

    for i, word in enumerate(search_words):

        if len(buffer) == 0:
            if word.startswith("'"):
                delimiter = "'"

            elif word.startswith('"'):
                delimiter = '"'

            elif delimiter is not None:
                delimiter = None

        if delimiter is None:
            new_words.append(word)

        elif word.startswith(delimiter) and len(buffer) == 0:

            if (word != delimiter and word.endswith(
                    delimiter)) or word == delimiter + delimiter:  # ex:  "hello" (in a single word)
                new_words.append(word)
                delimiter = None

                if ReduceSettings._debug:
                    print("WORD ", word)
            else:
                buffer.append(word)  # the comment is split



        elif word.endswith(delimiter) and len(buffer) > 0:

            buffer.append(word)
            text = "".join(char for char in buffer)

            if ReduceSettings._debug:
                print("JOINED TEXT", text)
            elif "\n" in text:
                print("WARNING: JOINED TEXT", text)

            buffer = []
            delimiter = None
            new_words.append(text)


        elif len(buffer) > 0:
            buffer.append(word)

        else:
            new_words.append(word)

    return new_words

