from indy_gen.function import FunctionParameter, IndyFunction

from .utils import to_camel_case, go_param_string


_CALLBACK_ERRCHECK = '''
    if err != nil {
        panic("Invalid handle in callback!")
    }
'''

class GoTranslator:
    def __init__(self, output_path):
        self._output_path = output_path

    def translate(self, name, functions):
        go_functions = {f.name: GoFunction.from_indy_function(f) for f in functions.values()}

        if 'indy_open_wallet' in go_functions:
            open_wallet = go_functions['indy_open_wallet']
            result_strings = self._generate_result_strings(open_wallet)
            callback_name, callback_export, callback_code = self._generate_callback(open_wallet, result_strings[1], result_strings[2])
            print(result_strings)
            print(callback_name)
            print(callback_export)
            print(callback_code)

    def _generate_callback(self, go_function, result_initialisation, result_sending):
        callback_name = go_function.name + 'Callback'
        callback_export = '//export ' + callback_name
        callback_params = go_param_string(go_function.callback.parameters)
        signature = f'func {callback_name}({callback_params})'
        first_param_name = go_function.callback.parameters[0].name
        deregister = f'resCh, err := resolver.DeregisterCall({first_param_name})'
        callback_code = (f'{signature} {{\n\t{deregister}{_CALLBACK_ERRCHECK}\n'
                         f'\t{result_initialisation}{result_sending}\n}}')
        return callback_name, callback_export, callback_code

    def _generate_result_strings(self, go_function):
        if len(go_function.callback.parameters) > 2:
            return self._generate_result_strings_for_complex_result(go_function)
        else:
            return '', '', f'resCh <- {go_function.callback.parameters[0].name}'

    def _generate_result_strings_for_complex_result(self, go_function):
        result_struct_name = f'{go_function.name}Result'
        result_fields = go_function.callback.parameters[1:]
        struct_field_declarations = []
        for field in result_fields:
            struct_field_declarations.append(f'{field.name} {field.type}')
        field_declaration_string = '\n\t'.join(struct_field_declarations)
        struct_declaration = f'type {result_struct_name} struct {{\n\t{field_declaration_string}\n}}'

        struct_field_initialisations = []
        for field in result_fields:
            struct_field_initialisations.append(f'{field.name}: {field.name}')
        field_initialisation_string = ',\n\t\t'.join(struct_field_initialisations)
        struct_initialisation = f'res := &{result_struct_name} {{\n\t\t{field_initialisation_string},\n\t}}\n'

        return struct_declaration, struct_initialisation, '\tresCh <- res'



class GoFunction:
    TYPE_MAP = {
        'int32_t': 'int32',
        'const char*': '*C.char',
        'const char *': '*C.char',
        'const char * const': '*C.char',
        'const char *const': '*C.char',
        'char*': '*C.char',
        'void': '',
        'uint8_t*': '*C.char',
        'uint32_t': 'uint32',
        'unsigned int': 'uint32',
        'int32_t*': '*int32',
        'char**': '**C.char',
        'long': 'int',
        'unsigned long long': 'uint64',
    }


    @classmethod
    def from_indy_function(cls, indy_function):
        try:
            go_func_name = to_camel_case(indy_function.name.lstrip('indy_'))

            go_func_params = []
            for param in indy_function.parameters:
                if isinstance(param, IndyFunction):
                    go_func_params.append(cls.from_indy_function(param))
                else:
                    go_param_type = cls.TYPE_MAP[param.type]
                    go_param_name = to_camel_case(param.name)
                    go_param = FunctionParameter(go_param_name, go_param_type)
                    go_func_params.append(go_param)

            go_return_type = cls.TYPE_MAP[indy_function.return_type]

            if indy_function.callback:
                go_func_callback = cls.from_indy_function(indy_function.callback)
            else:
                go_func_callback = None

            return cls(go_func_name, go_return_type, go_func_params, go_func_callback)
        except Exception as e:
            raise Exception(f'Failed to creat go function {indy_function.name}. Exception {e}') from e

    def __init__(self, name, return_type, parameters, callback):
        self.name = name
        self.return_type = return_type
        self.parameters = parameters
        self.callback = callback

    def __str__(self):
        param_string = '\n\t'.join(str(param) for param in self.parameters)
        return (f'[GoFunction]\nName: {self.name}\nReturn type: {self.return_type}\n' +
                f'Parameters:\n\t{param_string}\n' +
                f'Callback: {str(self.callback)}\n')

    def __repr__(self):
        return str(self)
