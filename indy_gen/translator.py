from indy_gen.function import FunctionParameter, IndyFunction

from .utils import to_camel_case, go_param_string, types_string, c_param_string, names_string


_REGISTER_CALL = '''
	pointer, handle, resCh, err := resolver.RegisterCall("{function_name}")
	if err != nil {{
	    err = fmt.Errorf("Failed to register call for {function_name}. Error: %s", err)
	    return {result_var_names}
	}}
'''
_CALLBACK_ERRCHECK = '''
    if err != nil {
        panic("Invalid handle in callback!")
    }
'''
_C_CALL_CHECK = '''
    if code != 0 {{
        err = fmt.Errorf("Libindy returned code: %d", code)
        return {result_var_names}
    }}
'''
_RESULT_RETRIEVING = '''
    _res := <- resCh
    res := _res.({expected_type})
'''
_RESULT_RETRIEVING_CHECK_SINGLE = '''
    if res != 0 {{
        err = fmt.Errorf("Libindy returned code: %d", res)
        return err
    }}
'''
_RESULT_RETRIEVING_CHECK_MULTIPLE = '''
    if res.{code_field_name} != 0 {{
        err = fmt.Errorf("Libindy returned code: %d", res.{code_field_name})
        return {result_var_names}
    }}
'''

class GoTranslator:
    GO_TO_CGO_TYPES = {
        'string': '*C.char',
        'int32': 'int32_t',
        'uint32': 'uint32_t',
    }


    def __init__(self, output_path):
        self._output_path = output_path

    def translate(self, name, functions):
        go_functions = {f.name: GoFunction.from_indy_function(f) for f in functions.values()}

        funcs = []
        for name, c_func in functions.items():
            go_function = GoFunction.from_indy_function(c_func)
            result_strings = self._generate_result_strings(go_function)
            callback_name, callback_export, callback_code = self._generate_callback(go_function, result_strings[1], result_strings[2])
            c_proxy_name, c_proxy_declaration, c_proxy_extern, c_proxy_code = self._generate_c_proxy(c_func, callback_name)

            print(result_strings)
            print(callback_name)
            print(callback_export)
            print(callback_code)
            print(c_proxy_name)
            print(c_proxy_declaration)
            print(c_proxy_extern)
            print(c_proxy_code)
            core = self._generate_core(go_function, c_func.name, c_proxy_name, result_strings[3])
            print(core)


    def _generate_callback(self, go_function, result_initialisation, result_sending):
        callback_name = go_function.name[0].lower() + go_function.name[1:] + 'Callback'
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
            callback_res_name = go_function.callback.parameters[0].name
            callback_res_type = go_function.callback.parameters[0].type
            sending = f'resCh <- {callback_res_name}'
            receiving = _RESULT_RETRIEVING.format(expected_type=callback_res_type)
            receiving = f'{receiving}\n\t{_RESULT_RETRIEVING_CHECK_SINGLE}'
            return '', '', sending, receiving

    def _generate_result_strings_for_complex_result(self, go_function):
        function_name_lower = go_function.name[0].lower() + go_function.name[1:]
        result_struct_name = f'{function_name_lower}Result'
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

        return struct_declaration, struct_initialisation, '\tresCh <- res', _RESULT_RETRIEVING.format(expected_type='*' + result_struct_name)

    def _generate_c_proxy(self, indy_function, go_callback_name):
        try:
            extern_declaration_types = types_string(indy_function.callback.parameters)
            extern_declaration = f'extern void {go_callback_name}({extern_declaration_types});'
            c_proxy_name = indy_function.name + '_proxy'
            fp_param = FunctionParameter('fp', 'void *')
            handle_param = FunctionParameter('handle', 'int32_t')
            all_params = [fp_param, handle_param] + indy_function.parameters
            c_proxy_types_declaration = c_param_string(all_params)
            c_proxy_signature = f'{indy_function.return_type} {c_proxy_name}({c_proxy_types_declaration})'
            indy_function_types = types_string(all_params[1:])
            function_cast = f'{indy_function.return_type} (*func)({indy_function_types}, void *) = fp;'
            function_arguments = names_string(all_params[1:])
            function_invocation = f'return func({function_arguments}, &{go_callback_name});'
            c_proxy_code = f'{c_proxy_signature} {{\n\t{function_cast}\n\t{function_invocation}\n}}'
            return c_proxy_name, c_proxy_signature + ';', extern_declaration, c_proxy_code
        except Exception as e:
            raise Exception(f'Failed to generate function for: {indy_function.name}. Exception: {e}')

    def _generate_core(self, go_indy_function, indy_function_name, c_proxy_name, result_retrieval):
        return_parameters = go_indy_function.callback.parameters[1:]
        return_types = [param.type for param in return_parameters]
        return_types.pop()
        return_types.append('error')
        return_var_names = ['res_' + param.name for param in return_parameters]
        return_var_names[0], return_var_names[-1] = return_var_names[-1], return_var_names[0]
        return_var_names_string = ', '.join(return_var_names)
        return_vars_init = []
        for name, type in zip(return_var_names, return_types):
            return_vars_init.append(f'var {name} {type}')
        return_vars_init_string = '\n\t'.join(return_vars_init)

        return_types_string = ', '.join(return_types)

        params = go_param_string(go_indy_function.parameters[1:])

        signature = f'func {go_indy_function.name}({params}) ({return_types_string})'

        register_call = _REGISTER_CALL.format(function_name=indy_function_name,
                                              result_var_names=return_var_names_string)
        handle = FunctionParameter('handle', 'int32')
        variables = [handle] + go_indy_function.parameters

        variable_names, variable_setups = self._setup_variables(variables)
        variable_setup_string = '\n\n\t'.join(variable_setups)
        variable_names.insert(0, 'pointer')
        variable_names = ', '.join(variable_names)

        c_call = f'code := C.{c_proxy_name}({variable_names})'
        c_call_check = _C_CALL_CHECK.format(result_var_names=return_var_names_string)

        retrieval_check = _RESULT_RETRIEVING_CHECK_MULTIPLE.format(code_field_name=go_indy_function.callback.parameters[1].name,
                                                                   result_var_names=return_var_names_string)

        result_var_assignments = [f'{var_name} = res.{var_name.replace("res_", "")}' for var_name in return_var_names]
        result_var_assignment_string = '\n\t' + '\n\t'.join(result_var_assignments)

        return (f'{signature} {{\n\t{return_vars_init_string}\n\t{register_call}'
                f'\n\n\t{variable_setup_string}\n\t{c_call}\n\t{c_call_check}'
                f'\n\t{result_retrieval}\n\t{retrieval_check}'
                f'\t{result_var_assignment_string}\n\treturn {return_var_names_string}\n}}')


    def _setup_variables(self, variables):
        variable_names = []
        variable_setups = []

        for var in variables:
            name, setup = self._setup_var(var)
            variable_names.append(name)
            variable_setups.append(setup)

        return variable_names, variable_setups

    def _setup_var(self, var):
        c_var_name = 'c_' + var.name
        c_var_type = self.GO_TO_CGO_TYPES[var.type]
        var_declaration = f'var {c_var_name} {c_var_type}'
        if var.type == 'string':
            setup = (f'if {var.name} != "" {{\n\t\t{c_var_name} = C.CString({var.name})\n\t\t'
                     f'defer C.free(unsafe.Pointer({c_var_name}))\n\t}}')
        elif var.type == 'int32':
            setup = f'{c_var_name} = C.int32_t({var.name})'
        elif var.type == 'uint32':
            setup = f'{c_var_name} = C.uint32_t({var.name})'
        else:
            raise Exception(f'No setup for var type: {var.type}')

        setup = f'{var_declaration}\n\t{setup}'

        return c_var_name, setup



class GoFunction:
    TYPE_MAP = {
        'int32_t': 'int32',
        'const char*': 'string',
        'const char *': 'string',
        'const char * const': 'string',
        'const char *const': 'string',
        'char*': 'string',
        'void': '',
        'uint8_t*': 'string',
        'uint32_t': 'uint32',
        'unsigned int': 'uint32',
        'int32_t*': '*int32',
        'char**': '*string',
        'long': 'int',
        'unsigned long long': 'uint64',
    }

    API_TYPE_MAP = {
        '*C.char': 'string',
    }


    @classmethod
    def from_indy_function(cls, indy_function):
        try:
            camel_case_name = to_camel_case(indy_function.name.lstrip('indy_'))
            go_func_name = camel_case_name[0].title() + camel_case_name[1:]

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
