import os
import re


class GeneratorError(Exception):
    pass


def split_into_parameters(params_string):
    param_strings = []

    levels = 0
    last_index = 0
    for i, char in enumerate(params_string):
        if char == '(':
            levels += 1
        elif char == ')':
            levels -= 1
        elif char == ',':
            if levels == 0:
                parameter_string = params_string[last_index:i]
                parameter_string = re.sub('(\n|\t|\s+)', ' ', parameter_string).strip()
                param_strings.append(parameter_string)
                last_index = i + 1

    last_param = params_string[last_index:]
    last_param = re.sub('(\n|\t|\s+)', ' ', last_param).strip()
    param_strings.append(last_param)

    return param_strings


class FunctionParameter:
    __slots__ = 'name', 'type'


    @classmethod
    def parse_from_string(cls, string):
        parts = string.split(' ')
        name = parts[-1]
        type = ' '.join(parts[:-1])
        return cls(name, type)


    def __init__(self, name, type):
        self.name = name
        self.type = type


class IndyFunction:
    __slots__ = 'name', 'return_type', 'parameters', 'callback'
    DECLARATION_REGEX = re.compile("(?P<rtype>[A-Za-z0-9-_]+?)\s\((?P<name>[*\sA-Za-z0-9_-]+?)\)\((?P<params>.*?)\)", re.DOTALL)
    INDY_DECLARATION_REGEX = re.compile("[extern]\s(?P<rtype>[A-Za-z0-9_-]+?)\s(?P<name>.*?)\((?P<params>.*?),\s+?(?P<callback>void\s+\(.*?\*.*?\)\(.*?\))", re.DOTALL)


    @staticmethod
    def parse_parameter_string(string):
        parameter_strings = split_into_parameters(string)
        parameters = []
        for parameter_string in parameter_strings:
            if ')' in parameter_string:
                parameters.append(IndyFunction.parse_from_string(parameter_string))
            else:
                parameters.append(FunctionParameter.parse_from_string(parameter_string))
        return parameters

    @classmethod
    def parse_from_header_content(cls, content):
        content = re.sub('(\n|\t|\s+)', ' ', content)
        functions = {}

        for result in re.finditer(cls.INDY_DECLARATION_REGEX, content):
            result_dict = result.groupdict()
            return_type = result_dict['rtype']
            name = result_dict['name']
            params_string = result_dict['params']
            parameters = cls.parse_parameter_string(params_string)

            callback_string = result_dict['callback']
            callback = cls.parse_from_string(callback_string)

            indy_function = cls(name, return_type, parameters, callback)
            functions[name] = indy_function

        return functions


    @classmethod
    def parse_from_string(cls, string):
        result = re.match(cls.DECLARATION_REGEX, string)
        if not result:
            raise GeneratorError(f'Failed to pattern match function string: {string}')

        result_dict = result.groupdict()
        return_type = result_dict['rtype']
        name = result_dict['name']
        params_string = result_dict['params']
        parameters = cls.parse_parameter_string(params_string)

        return cls(name, return_type, parameters)


    def __init__(self, name, return_type, parameters, callback=None):
        self.name = name
        self.return_type = return_type
        self.parameters = parameters
        self.callback = callback


class HeaderParser:
    TYPEDEF_REGEX = re.compile("typedef (?P<original_type>[A-Za-z0-9_-]+?)\s+?(?P<alias>[A-Za-z0-9_-]+);")



    def __init__(self, header_path):
        self._header_path = header_path

    def parse_indy_header_files(self):
        file_names = os.listdir(self._header_path)
        header_file_names = [name for name in file_names if name.endswith('.h')]
        if "indy_types.h" in header_file_names:
            header_file_names.remove('indy_types.h')
            indy_types = self._parse_indy_type_aliases("indy_types.h")
        else:
            indy_types = {}

        indy_types['indy_error_t'] = 'int32_t'

        function_declarations = {}
        for header_name in header_file_names:
            declarations = self._parse_function_declarations(header_name)
            function_declarations[header_name] = declarations

        return function_declarations, indy_types

    # TODO - private
    def _parse_indy_type_aliases(self, types_file_name):
        with open(os.path.join(self._header_path, types_file_name), 'r') as f:
            content = f.read()

        type_aliases = {}
        for result in re.finditer(self.TYPEDEF_REGEX, content):
            result_dict = result.groupdict()
            type_aliases[result_dict['alias']] = result_dict['original_type']

        return type_aliases

    def _parse_function_declarations(self, header_name):
        with open(os.path.join(self._header_path, header_name), 'r') as f:
            content = f.read()

        return IndyFunction.parse_from_header_content(content)



class Generator:
    def __init__(self, output_path, header_path):
        self._output_path = output_path
        self._header_path = header_path

    def generate_output_files(self):
        header_file_contents = self._parse_indy_header_files()



def demo():
    header_path = "/home/keichiri/code/indy-sdk/libindy/include"
    output_path = "/home/keichiri/code/indy-gen"
    header_parser = HeaderParser(header_path)
    res = split_into_parameters(x)
    print(len(res))
    print(res[-1])



if __name__ == '__main__':
    demo()