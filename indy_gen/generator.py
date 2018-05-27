import os
import re

from indy_gen.function import FunctionParameter, IndyFunction
from indy_gen.translator import GoTranslator


class GeneratorError(Exception):
    pass



class HeaderParser:
    TYPEDEF_REGEX = re.compile("typedef\s(?P<original_type>[\sA-Za-z0-9_-]+?)\s+?(?P<alias>[A-Za-z0-9_-]+);")


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
            for declaration in declarations.values():
                declaration.resolve_type_aliases(indy_types)
            function_declarations[header_name] = declarations

        return function_declarations

    # TODO - private
    def _parse_indy_type_aliases(self, types_file_name):
        with open(os.path.join(self._header_path, types_file_name), 'r') as f:
            content = f.read()
            content = re.sub('//[/].*?\n', '', content)

        type_aliases = {}
        for result in re.finditer(self.TYPEDEF_REGEX, content):
            result_dict = result.groupdict()
            type_aliases[result_dict['alias']] = result_dict['original_type']

        return type_aliases

    def _parse_function_declarations(self, header_name):
        with open(os.path.join(self._header_path, header_name), 'r') as f:
            content = f.read()
            content = re.sub('//[/].*?\n', '', content)

        return IndyFunction.parse_from_header_content(content)



class Generator:
    def __init__(self, output_path, header_path):
        self._output_path = output_path
        self._header_path = header_path
        self._header_parser = HeaderParser(header_path)
        self._go_translator = GoTranslator(self._output_path)

    def generate_output_files(self):
        declarations = self._header_parser.parse_indy_header_files()

        for domain, declarations in declarations.items():
            self._go_translator.translate(domain, declarations)

