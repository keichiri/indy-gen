import re

from .utils import split_into_parameters


class FunctionParameter:
    __slots__ = 'name', 'type', 'original_type', 'qualifiers'


    @classmethod
    def parse_from_string(cls, string):
        split = string.split(' ')
        parts = []
        for s in split:
            if s == '*' or s == '**':
                parts[-1] += s
            elif 'const' in s:
                if '*' in s:
                    parts[-1] += '*'
            else:
                parts.append(s)
        name = parts[-1]
        type = parts[-2]
        qualifiers = parts[:-2]
        return cls(name, type, qualifiers)


    def __init__(self, name, type, original_type=None, qualifiers=None):
        if name == 'type':
            name = 'type_'
        self.name = name
        self.type = type
        self.original_type = original_type
        if not qualifiers:
            self.qualifiers = []
        else:
            self.qualifiers = qualifiers

    def resolve_type_aliases(self, aliases):
        try:
            self.type = aliases[self.type]
        except KeyError:
            if self._is_pointer():
                pointed_type, indirection_count = self._strip_pointer()
                new_pointed_type = aliases.get(pointed_type)
                if new_pointed_type:
                    self.type = new_pointed_type + '*' * indirection_count


    def _is_pointer(self):
        return '*' in self.type

    def _strip_pointer(self):
        return self.type.replace('*', ''), self.type.count('*')

    def __str__(self):
        return f'Name: {self.name} Type: {self.type}. Qualifiers: {self.qualifiers}'



class IndyFunction:
    __slots__ = 'name', 'return_type', 'parameters', 'callback'
    DECLARATION_REGEX = re.compile("(?P<rtype>[A-Za-z0-9-_]+?)\s\((?P<name>[*\sA-Za-z0-9_-]+?)\)\((?P<params>.*?)\)", re.DOTALL)
    INDY_DECLARATION_REGEX = re.compile("[extern][\s](?P<rtype>[A-Za-z0-9_-]+?)\s(?P<name>[*\sA-Za-z0-9_-]+?)\((?P<params>[\s\n,\*\(\)A-Za-z0-9_-]*?),\s+?(?P<callback>void\s+\(.*?\*.*?\)\(.*?\))", re.DOTALL)


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

    def resolve_type_aliases(self, aliases):
        self.return_type = aliases.get(self.return_type, self.return_type)
        for param in self.parameters:
            param.resolve_type_aliases(aliases)
        if self.callback:
            self.callback.resolve_type_aliases(aliases)

    def __str__(self):
        param_string = '\n\t'.join(str(param) for param in self.parameters)
        return (f'[IndyFunction]\nName: {self.name}\nReturn type: {self.return_type}\n' +
                f'Parameters:\n\t{param_string}\n' +
                f'Callback: {str(self.callback)}\n')

    def __repr__(self):
        return str(self)

    @property
    def type(self):
        return 'void *'
