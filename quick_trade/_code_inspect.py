import inspect


def get_caller_name(level: int = 1):
    return inspect.stack()[level + 1].function  # +1 because this function is a part of project file


def format_arguments(func,
                     args: tuple = (),
                     kwargs: dict = {}):
    if isinstance(func, str):
        f_name = func
    else:
        f_name = func.__code__.co_name
    # sorting dict by keys
    sorted_dict = {}
    for key in sorted(kwargs):
        sorted_dict[key] = kwargs[key]

    args_format = repr(args)[1:-1]
    kwargs_format = str(sorted_dict).replace(": ", "=").replace("'", "").strip("{").strip("}")
    if kwargs_format and args_format:
        sep = ', '
    else:
        sep = ''
    return f'{f_name}({args_format}{sep}{kwargs_format})'
