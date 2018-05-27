import re


def c_param_string(params):
    return ', '.join(f'{p.type} {p.name}' for p in params)

def go_param_string(params):
    return ', '.join(f'{p.name} {p.type}' for p in params)


def types_string(params):
    return ', '.join(p.type for p in params)


def to_camel_case(function_name):
    words = function_name.split('_')
    return ''.join([words[0]] + [word.capitalize() for word in words[1:]])


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