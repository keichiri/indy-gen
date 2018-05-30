import os

from indy_gen.function import FunctionParameter, IndyFunction

from .utils import to_camel_case, go_param_string, types_string, c_param_string, names_string


_REGISTER_CALL = '''
	pointer, commandHandle, resCh, err := resolver.RegisterCall("{function_name}")
	if err != nil {{
	    err = fmt.Errorf("Failed to register call for {function_name}. Error: %s", err)
	    return {result_var_names}
	}}
'''
_CALLBACK_ERRCHECK = '''
    if deregisterErr != nil {
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
    if res != 0 {
        err = fmt.Errorf("Libindy returned code: %d", res)
'''
_RESULT_RETRIEVING_CHECK_MULTIPLE = '''
    if res.{code_field_name} != 0 {{
        err = fmt.Errorf("Libindy returned code: %d", res.{code_field_name})
'''

class GoTranslator:
    GO_TO_CGO_TYPES = {
        'string': '*C.char',
        'int32': 'int32_t',
        'uint32': 'uint32_t',
        'int': 'int64_t',
        'uint64': 'uint64_t',
        '*uint8': '*C.uint8_t'
    }

    C_TO_CGO_TYPES = {
        'unsigned long long': 'C.ulonglong',
        'int32_t': 'C.int32_t',
        'uint32_t': 'C.uint32_t',
        'unsigned int': 'C.uint',
        'long': 'C.long',
        'uint8_t*': 'C.uint8_t'
    }


    def __init__(self, output_path):
        self._output_path = output_path

    def translate(self, name, functions):
        callbacks = []
        c_proxy_declarations = []
        c_proxy_extern_declarations = []
        c_proxies = []
        result_struct_definitions = []
        cores = []

        for func_name, c_func in functions.items():
            go_function = GoFunction.from_indy_function(c_func)
            result_strings = self._generate_result_strings(go_function)
            callback_name, callback_code = self._generate_callback(go_function, result_strings[1], result_strings[2])
            c_proxy_name, c_proxy_declaration, c_proxy_extern, c_proxy_code = self._generate_c_proxy(c_func, callback_name)
            core_code = self._generate_core(go_function, c_func.name, c_proxy_name, result_strings[3])

            callbacks.append(callback_code)
            c_proxy_declarations.append(c_proxy_declaration)
            c_proxy_extern_declarations.append(c_proxy_extern)
            c_proxies.append(c_proxy_code)
            cores.append(core_code)
            result_struct_definitions.append(result_strings[0])

        if cores:
            self._populate_c_file(name, c_proxy_extern_declarations, c_proxies)
            self._populate_go_file(name, c_proxy_declarations, callbacks, result_struct_definitions, cores)

    def _populate_c_file(self, domain, extern_declarations, proxies):
        full_path = os.path.join(self._output_path, domain + '.c')

        with open(full_path, 'w') as f:
            f.write('#include <stdint.h>\n\n')
            f.write('\n'.join(extern_declarations))
            f.write('\n\n\n')
            f.write('\n\n\n'.join(proxies))
            f.write('\n')

    def _populate_go_file(self, domain, c_proxy_declarations, callbacks, result_struct_defintions, core_functions):
        full_path = os.path.join(self._output_path, domain + '.go')

        with open(full_path, 'w') as f:
            f.write('package indy\n\n')
            f.write('/*\n')
            f.write('#include <stdlib.h>\n')
            f.write('#include <stdint.h>\n')
            f.write('\n'.join(c_proxy_declarations))
            f.write('\n')
            f.write('*/\n')
            f.write('import "C"\n\n')
            f.write('import (\n\t"fmt"\n\t"unsafe"\n)\n\n')
            f.write('\n\n'.join(core_functions))
            f.write('\n\n')
            f.write('\n\n'.join(result_struct_defintions))
            f.write('\n\n')
            f.write('\n\n'.join(callbacks))
            f.write('\n\n')

    def _generate_callback(self, go_function, result_initialisation, result_sending):
        callback_name = go_function.name[0].lower() + go_function.name[1:] + 'Callback'
        callback_export = '//export ' + callback_name
        callback_params = go_param_string(go_function.callback.parameters)
        signature = f'func {callback_name}({callback_params})'
        first_param_name = go_function.callback.parameters[0].name
        deregister = f'resCh, deregisterErr := resolver.DeregisterCall({first_param_name})'
        callback_code = (f'{callback_export}\n{signature} {{\n\t{deregister}{_CALLBACK_ERRCHECK}\n'
                         f'\t{result_initialisation}{result_sending}\n}}')
        return callback_name, callback_code

    def _generate_result_strings(self, go_function):
        if len(go_function.callback.parameters) > 2:
            return self._generate_result_strings_for_complex_result(go_function)
        else:
            callback_res_name = go_function.callback.parameters[0].name
            callback_res_type = go_function.callback.parameters[0].type
            sending = f'resCh <- {callback_res_name}'
            receiving = _RESULT_RETRIEVING.format(expected_type=callback_res_type)
            receiving = f'{receiving}\t{_RESULT_RETRIEVING_CHECK_SINGLE}'
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
        receiving = _RESULT_RETRIEVING.format(expected_type='*' + result_struct_name)
        struct_err_field_name = go_function.callback.parameters[1].name
        receiving += f'\t{_RESULT_RETRIEVING_CHECK_MULTIPLE}'.format(code_field_name=struct_err_field_name)

        return struct_declaration, struct_initialisation, '\tresCh <- res', receiving

    def _generate_c_proxy(self, indy_function, go_callback_name):
        extern_declaration_types = types_string(indy_function.callback.parameters)
        extern_declaration = f'extern void {go_callback_name}({extern_declaration_types});'
        c_proxy_name = indy_function.name + '_proxy'
        fp_param = FunctionParameter('fp', 'void *')
        all_params = [fp_param] + indy_function.parameters
        c_proxy_declaration = f'{indy_function.return_type} {c_proxy_name}({types_string(all_params)});'
        c_proxy_types_declaration = c_param_string(all_params)
        c_proxy_signature = f'{indy_function.return_type} {c_proxy_name}({c_proxy_types_declaration})'
        indy_function_types = types_string(all_params[1:])
        function_cast = f'{indy_function.return_type} (*func)({indy_function_types}, void *) = fp;'
        function_arguments = names_string(all_params[1:])
        function_invocation = f'return func({function_arguments}, &{go_callback_name});'
        c_proxy_code = f'{c_proxy_signature} {{\n\t{function_cast}\n\t{function_invocation}\n}}'
        return c_proxy_name, c_proxy_declaration, extern_declaration, c_proxy_code

    def _generate_core(self, go_indy_function, indy_function_name, c_proxy_name, result_retrieval):
        if go_indy_function.name == 'CryptoSign':
            x = 3
        return_parameters = go_indy_function.callback.parameters[1:]
        return_parameters[0], return_parameters[-1] = return_parameters[-1], return_parameters[0]
        return_types = [param.type for param in return_parameters]
        return_var_names = ['res_' + param.name for param in return_parameters]
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
        # handle = FunctionParameter('commandHandle', 'int32')
        # variables = [handle] + go_indy_function.parameters
        variables = go_indy_function.parameters

        variable_names, variable_passing, variable_setups = self._setup_variables(variables)
        variable_setup_string = '\n\n\t'.join(variable_setups)
        variable_names.insert(0, 'pointer')
        variable_passing.insert(0, 'pointer')
        variable_names = ', '.join(variable_passing)

        c_call = f'code := C.{c_proxy_name}({variable_names})'
        c_call_check = _C_CALL_CHECK.format(result_var_names=return_var_names_string)

        result_var_assignments = [f'{var_name} = res.{var_name.replace("res_", "")}' for var_name in return_var_names
                                  if var_name != 'res_err']
        result_var_assignment_string = '\n\t' + '\n\t'.join(result_var_assignments)
        retrieval_and_check = result_retrieval + f'\t\treturn {return_var_names_string}\n\t}}\n'

        return (f'{signature} {{\n\t{return_vars_init_string}\n\t{register_call}'
                f'\n\n\t{variable_setup_string}\n\n\t{c_call}\t{c_call_check}'
                f'\t{retrieval_and_check}'
                f'\t{result_var_assignment_string}\n\n\treturn {return_var_names_string}\n}}')

    def _setup_variables(self, variables):
        variable_names = []
        variable_passings = []
        variable_setups = []

        for var in variables:
            if isinstance(var, GoFunction):
                name, passing, setup = self._setup_func_var(var)
            else:
                name, passing, setup = self._setup_var(var)
            variable_names.append(name)
            variable_passings.append(passing)
            variable_setups.append(setup)

        return variable_names, variable_passings, variable_setups

    def _setup_func_var(self, var):
        c_var_name = 'c_' + var.name
        var_declaration = f'var {c_var_name} unsafe.Pointer'
        setup = f'{var_declaration}\n\t{c_var_name} = unsafe.Pointer(&{var.name})'
        return c_var_name, c_var_name, setup

    def _setup_var(self, var):
        c_var_name = 'c_' + var.name
        passing = c_var_name
        c_var_type = self.GO_TO_CGO_TYPES[var.type]
        if var.type == 'string':
            var_declaration = f'var {c_var_name} {c_var_type}'
            setup = (f'if {var.name} != "" {{\n\t\t{c_var_name} = C.CString({var.name})\n\t\t'
                     f'defer C.free(unsafe.Pointer({c_var_name}))\n\t}}')
            setup = f'{var_declaration}\n\t{setup}'
        elif var.type == 'int32':
            setup = f'{c_var_name} := {self.C_TO_CGO_TYPES[var.original_type]}({var.name})'
        elif var.type == 'uint32':
            setup = f'{c_var_name} := {self.C_TO_CGO_TYPES[var.original_type]}({var.name})'
        elif var.type == 'int':
            setup = f'{c_var_name} := {self.C_TO_CGO_TYPES[var.original_type]}({var.name})'
        elif var.type == 'uint64':
            setup = f'{c_var_name} := {self.C_TO_CGO_TYPES[var.original_type]}({var.name})'
        elif var.type == '*uint8':
            setup = f'{c_var_name} := {self.C_TO_CGO_TYPES[var.original_type]}(*{var.name})'
            passing = '&' + passing
        else:
            raise Exception(f'No setup for var type: {var.type}')

        return c_var_name, passing, setup



class GoFunction:
    TYPE_MAP = {
        'int32_t': 'int32',
        'const char*': 'string',
        'const char *': 'string',
        'const char * const': 'string',
        'const char *const': 'string',
        'char*': 'string',
        'void': '',
        'uint8_t*': '*uint8',
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
            camel_case_name = to_camel_case(indy_function.name.replace('indy_', ''))
            go_func_name = camel_case_name[0].title() + camel_case_name[1:]

            go_func_params = []
            for param in indy_function.parameters:
                if isinstance(param, IndyFunction):
                    go_func_params.append(cls.from_indy_function(param))
                else:
                    go_param_type = cls.TYPE_MAP[param.type]
                    go_param_name = to_camel_case(param.name)
                    go_param = FunctionParameter(go_param_name, go_param_type, original_type=param.type)
                    go_func_params.append(go_param)

            go_return_type = cls.TYPE_MAP[indy_function.return_type]

            if indy_function.callback:
                go_func_callback = cls.from_indy_function(indy_function.callback)
            else:
                go_func_callback = None

            return cls(go_func_name, go_return_type, go_func_params, go_func_callback)
        except Exception as e:
            raise Exception(f'Failed to create go function {indy_function.name}. Exception {e}') from e

    def __init__(self, name, return_type, parameters, callback):
        name = name.replace('*', '')
        if name == 'type':
            name = 'type_'
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

    @property
    def type(self):
        return f'func({types_string(self.parameters)})({self.return_type})'