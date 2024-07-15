#!/usr/bin/python3

#
#  Copyright (C) 2022-2023 Rafael Senties Martinelli. All Rights Reserved.
#

from collections import OrderedDict


class ReduceData:

    def __init__(self):

        self.errors = []
        self.constants = OrderedDict()
        self.functions = OrderedDict()
        self.clases = OrderedDict()

    def add_constant(self, name, encode):

        if name not in self.constants.keys():
            self.constants[name] = ReduceConstant(name, encode)

        else:
            self.add_error("Constant already declared " + name)

    def add_function(self, name, encode):

        if name not in self.functions.keys():
            self.functions[name] = ReduceFunction(name, encode)

        else:
            self.add_error("Function already declared " + name)

    def add_class(self, name):

        if name not in self.clases.keys():
            self.clases[name] = ReduceClass(name)

        else:
            self.add_error("Class already declared " + name)

    def add_method(self, name, method_name):

        class_data = self.__get_class(name)

        if class_data is not None:

            added = class_data.add_method(method_name)

            if not added:
                self.add_error("add_method already declared '" + method_name + "' on class " + name)

    def get_method_encode(self, name, method_name):

        class_data = self.__get_class(name)

        if class_data is None:
            return None

        return class_data.get_method_encode(method_name)

    def get_replace_method_names(self, name):

        data = {}

        class_data = self.__get_class(name)

        if class_data is not None:

            for method in class_data.methods.values():
                if method.encode is not None:
                    data[method.name] = method.encode

        return data

    def get_replace_properties(self, name):

        class_data = self.__get_class(name)

        if class_data is None:
            return {}

        return class_data.properties

    def add_property(self, name, prop_name):

        class_data = self.__get_class(name)

        if class_data is not None:
            class_data.add_property(prop_name)

    def add_method_arg(self, name, method_name, arg_name):

        class_data = self.__get_class(name)

        if class_data is not None:

            added = class_data.add_method_arg(method_name, arg_name)

            if not added:
                self.add_error("add_method_arg " + name + "." + method_name + " " + arg_name)

    def add_constant_parameter(self, name, param_name):

        try:
            constant = self.constants[name]
        except Exception:
            self.add_error("constant not found: " + name)
            return False, None

        added, encode = constant.add_parameter(param_name)

        if not added:
            self.add_error("add_constant_parameter " + name + " " + param_name)
            return False, None

        return True, encode

    def get_method_args(self, name, method_name):

        class_data = self.__get_class(name)

        if class_data is None:
            return {}

        try:
            method = class_data.methods[method_name]
        except Exception:
            self.add_error("get_method_args method not found: " + name + "." + method_name)
            return {}

        return method.arguments

    def add_method_var(self, name, method_name, var_name):

        class_data = self.__get_class(name)

        if class_data is not None:

            added = class_data.add_method_var(method_name, var_name)

            if added is None:
                pass

            elif not added:
                self.add_error("add_method_var " + name + "." + method_name + " " + var_name)

    def get_method_vars(self, name, method_name):

        class_data = self.__get_class(name)

        if class_data is None:
            return {}

        try:
            method = class_data.methods[method_name]
        except Exception:
            self.add_error("get_method_vars method not found: " + name + "." + method_name)
            return {}

        return method.variables

    def add_method_const(self, name, method_name, const_name):

        class_data = self.__get_class(name)

        if class_data is not None:

            added = class_data.add_method_const(method_name, const_name)

            if added is None:
                pass

            elif not added:
                self.add_error("add_method_const " + name + "." + method_name + " " + const_name)

    def get_method_constants(self, name, method_name):

        class_data = self.__get_class(name)

        if class_data is None:
            return {}

        try:
            method = class_data.methods[method_name]
        except Exception:
            self.add_error("get_method_constants method not found: " + name + "." + method_name)
            return {}

        return method.constants

    def add_method_let(self, name, method_name, let_name):

        class_data = self.__get_class(name)

        if class_data is not None:

            added = class_data.add_method_let(method_name, let_name)

            if added is None:
                pass

            elif not added:
                self.add_error("add_method_let " + name + "." + method_name + " " + let_name)

    def get_method_lets(self, name, method_name):

        class_data = self.__get_class(name)

        if class_data is None:
            return {}

        try:
            method = class_data.methods[method_name]
        except Exception:
            self.add_error("get_method_lets method not found: " + name + "." + method_name)
            return {}

        return method.lets

    def add_function_arg(self, function_name, arg_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return

        added = function.add_argument(arg_name)

        if not added:
            self.add_error("add_function_arg " + function_name + " " + arg_name)

    def get_function_args(self, function_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return {}

        return function.arguments

    def add_function_var(self, function_name, var_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return

        added = function.add_variable(var_name)

        if added is None:  # duplicated entries may happen: ex: if (true){var a = 1{else}var a = 2
            pass

        elif not added:
            self.add_error("add_function_var " + function_name + " " + var_name)

    def get_function_vars(self, function_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return {}

        return function.variables

    def add_function_let(self, function_name, let_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return

        added = function.add_let(let_name)

        if added is None:  # duplicated entries may happen: ex: if (true){let a = 1{else}let a = 2
            pass

        elif not added:
            self.add_error("add_function_let " + function_name + " " + let_name)

    def get_function_lets(self, function_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return {}

        return function.lets

    def add_function_const(self, function_name, const_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return

        added = function.add_constant(const_name)

        if added is None:  # duplicated entries may happen: ex: if (true){const a = 1{else}const a = 2
            pass

        elif not added:
            self.add_error("add_function_const " + function_name + " " + const_name)

    def get_function_constants(self, function_name):

        try:
            function = self.functions[function_name]
        except Exception:
            self.add_error("function not found: " + function_name)
            return {}

        return function.constants

    def __get_class(self, name):

        try:
            class_data = self.clases[name]
        except Exception:
            self.add_error("Class not found: " + name)
            return None

        return class_data

    def add_error(self, text):

        text = "[Error] " + text
        self.errors.append(text)

    def __str__(self):

        string_data = ""

        if len(self.errors) > 0:
            string_data += "\n"
            string_data += "\n".join(error for error in self.errors)
            string_data += "\n"

        if len(self.constants.keys()) > 0:
            string_data += "\n"
            for value in self.constants.values():
                string_data += str(value) + "\n"

        if len(self.functions.keys()) > 0:
            string_data += "\n"
            for value in self.functions.values():
                string_data += str(value) + "\n"

        if len(self.clases.keys()) > 0:
            string_data += "\n"
            for value in self.clases.values():
                string_data += str(value) + "\n"

        return string_data


class ReduceClass:

    def __init__(self, name, encode=None):

        self.name = name
        self.encode = encode
        self.properties = OrderedDict()
        self.methods = OrderedDict()

    def __str__(self):

        if self.encode is None:
            string_data = self.name + ":"
        else:
            string_data = "{}:{}".format(self.encode, self.name)

        if len(self.properties.keys()) > 0:

            string_data += "\n"

            for name, encode in self.properties.items():
                row1 = "\n\tthis." + encode
                row2 = "\tthis." + name

                string_data += "{:<150} {}".format(row1, row2)

            string_data += "\n"

        if len(self.methods.values()) > 0:
            string_data += "\n"
            for value in self.methods.values():
                string_data += str(value) + "\n"

        return string_data

    def add_property(self, method_name):

        if method_name not in self.properties.keys():
            current_count = len(self.properties.keys())
            self.properties[method_name] = "p" + str(current_count)
            return True

        return False

    def add_method(self, method_name):

        if method_name not in self.methods.keys():

            if method_name.startswith("__"):
                current_count = len(
                    [method_name for method_name in self.methods.keys() if method_name.startswith("__")]) + 1
                method_encode = "m" + str(current_count)

            else:
                method_encode = None

            self.methods[method_name] = ReduceMethod(method_name, method_encode)
            return True

        return False

    def get_method_encode(self, method_name):

        try:
            return self.methods[method_name].encode
        except Exception:
            return None

    def add_method_arg(self, method_name, arg_name):

        if method_name in self.methods.keys():
            method = self.methods[method_name]
            added = method.add_argument(arg_name)

            return added

        return False

    def add_method_var(self, method_name, var_name):

        if method_name in self.methods.keys():
            method = self.methods[method_name]
            added = method.add_variable(var_name)

            return added

        return False

    def add_method_const(self, method_name, const_name):

        if method_name in self.methods.keys():
            method = self.methods[method_name]
            added = method.add_constant(const_name)

            return added

        return False

    def add_method_let(self, method_name, let_name):

        if method_name in self.methods.keys():
            method = self.methods[method_name]
            added = method.add_let(let_name)

            return added

        return False


class ReduceConstant:
    """
        const __PDATA_STATUS = {
            created : 10,
            uploading : 20,
        };
    """

    def __init__(self, name, encode):

        self.name = name
        self.encode = encode

        self.parameters = OrderedDict()

    def add_parameter(self, name):

        if name not in self.parameters.keys():
            encode = "p{}".format(len(self.parameters))
            self.parameters[name] = encode
            return True, encode

        return False, None

    def __str__(self):
        text = "\n const {:<150} {}".format(self.encode, self.name)

        if len(self.parameters) > 0:
            for key, value in self.parameters.items():
                text += "\n    {}:{}".format(value, key)

        return text


class ReduceFunction:

    def __init__(self, name, encode):

        self.name = name
        self.encode = encode

        self.arguments = OrderedDict()
        self.variables = OrderedDict()
        self.constants = OrderedDict()
        self.lets = OrderedDict()

    def __str__(self):

        arguments = ", ".join("{}:{}".format(value, key) for key, value in self.arguments.items())

        if self.encode is None:
            header = " function {}({})".format(self.name, arguments)
        else:
            row1 = "{}({})".format(self.encode, arguments)
            header = " function {:<150} {}".format(row1, self.name)

        if len(self.variables.keys()) > 0:
            header += "\n"
            header += "\n".join(
                ("\t{}:{}".format(var_encode, var_name) for var_name, var_encode in self.variables.items()))
            header += "\n"

        if len(self.constants.keys()) > 0:
            header += "\n"
            header += "\n".join(
                ("\t{}:{}".format(const_encode, const_name) for const_name, const_encode in self.constants.items()))
            header += "\n"

        if len(self.lets.keys()) > 0:
            header += "\n"
            header += "\n".join(("\t{}:{}".format(let_encode, let_name) for let_name, let_encode in self.lets.items()))
            header += "\n"

        return header

    def add_argument(self, arg_name):
        check_list = list(self.variables.keys()) + list(self.constants.keys()) + list(self.lets.keys())
        return self.__add_to(arg_name, "a", self.arguments, check_list, False)

    def add_variable(self, var_name):
        check_list = list(self.arguments.keys()) + list(self.constants.keys()) + list(self.lets.keys())
        return self.__add_to(var_name, "v", self.variables, check_list, True)

    def add_constant(self, const_name):
        check_list = list(self.arguments.keys()) + list(self.variables.keys()) + list(self.lets.keys())
        return self.__add_to(const_name, "c", self.constants, check_list, True)

    def add_let(self, let_name):
        check_list = list(self.arguments.keys()) + list(self.variables.keys()) + list(self.constants.keys())
        return self.__add_to(let_name, "l", self.lets, check_list, True)

    @staticmethod
    def __add_to(name, encode_char, items_dict, check_list, skip_duplicated):

        if name in check_list:
            return False

        if name not in items_dict.keys():
            items_dict[name] = encode_char + str(len(items_dict.keys()) + 1)
            return True

        elif skip_duplicated:
            return None
        else:
            return False


class ReduceMethod(ReduceFunction):

    def __init__(self, name, encode):
        super().__init__(name, encode)

    def __str__(self):

        arguments = ", ".join("{}:{}".format(value, key) for key, value in self.arguments.items())

        if self.encode is None:
            header = "\t{}({})".format(self.name, arguments)

        else:
            row1 = "\t{}({})".format(self.encode, arguments)
            header = "{:<150} {}".format(row1, self.name)

        if len(self.variables.keys()) > 0:
            header += "\n"
            header += "\n".join(
                ("\t   {}:{}".format(var_encode, var_name) for var_name, var_encode in self.variables.items()))
            header += "\n"

        if len(self.constants.keys()) > 0:
            header += "\n"
            header += "\n".join(
                ("\t   {}:{}".format(const_encode, const_name) for const_name, const_encode in self.constants.items()))
            header += "\n"

        if len(self.lets.keys()) > 0:
            header += "\n"
            header += "\n".join(
                ("\t   {}:{}".format(let_encode, let_name) for let_name, let_encode in self.lets.items()))
            header += "\n"

        return header
