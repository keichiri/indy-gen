from indy_gen.function import FunctionParameter, IndyFunction

from .utils import go_param_string, c_param_string, types_string, to_camel_case


class GoTranslator:
    def __init__(self, output_path):
        self._output_path = output_path

    def translate(self, name, functions):
        go_functions = {name: GoFunction.from_indy_function(f) for f in functions.values()}


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
