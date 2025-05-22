# -*- coding: utf-8 -*-


__all__ = [
    "loadCppData", "loadJSData", "loadShellData", "loadPHPData", "loadQMLData",
    "loadPythonData", "loadRustData", "loadJavaData", "loadCSharpData",
    "loadGoData", "loadVData", "loadSQLData", "loadJSONData", "loadCSSData",
    "loadTypeScriptData", "loadVexData", "loadCMakeData", "loadMakeData",
    "loadYAMLData", "loadNixData", "loadForthData", "loadSystemVerilogData",
    "loadGDScriptData", "loadTOMLData"
]

cpp_keywords = {
    'a': ["alignas", "alignof", "and", "and_eq", "asm"],
    'b': ["bit_and", "bit_or", "break"],
    'c': ["case", "catch", "compl", "concept", "const", "constinit", "constexpr", "consteval", "const_cast", "continue", "co_await", "co_return", "co_yield"],
    'd': ["decltype", "default", "delete", "do", "dynamic_cast"],
    'e': ["else", "explicit", "export", "extern"],
    'f': ["for", "friend"],
    'g': ["goto"],
    'i': ["if", "inline"],
    'm': ["mutable"],
    'n': ["new", "not", "not_eq", "noexcept"],
    'o': ["or", "or_eq", "operator"],
    'p': ["private", "protected", "public"],
    'r': ["register", "reinterpret_cast", "requires", "return"],
    's': ["signal", "sizeof", "slot", "static", "static_assert", "static_cast", "switch"],
    't': ["template", "this", "thread_local", "throw", "try", "typeid", "typedef", "typename"],
    'u': ["using"],
    'v': ["volatile"],
    'w': ["while"],
    'x': ["xor", "xor_eq"]
}

cpp_types = {
    'a': ["auto"],
    'b': ["bool"],
    'c': ["char", "char8_t", "char16_t", "char32_t", "class"],
    'd': ["double"],
    'e': ["enum"],
    'f': ["float"],
    'i': ["int", "int8_t", "int16_t", "int32_t", "int64_t", "int_fast8_t", "int_fast16_t", "int_fast32_t", "int_fast64_t", "intmax_t", "intptr_t"],
    'l': ["long"],
    'n': ["namespace"],
    'Q': ["QHash", "QList", "QMap", "QString", "QVector", "QMultiHash", "QLatin1String"],
    's': ["short", "size_t", "signed", "struct", "ssize_t"],
    'u': ["uint8_t", "uint16_t", "uint32_t", "uint64_t", "uint_fast8_t", "uint_fast16_t", "uint_fast32_t", "uint_fast64_t", "uint_least8_t", "uint_least16_t", "uint_least32_t", "uint_least64_t", "uintmax_t", "uintptr_t", "unsigned", "union"],
    'v': ["void"],
    'w': ["wchar_t"]
}

cpp_literals = {
    'f': ["false"],
    'n': ["nullptr"],
    'N': ["NULL"],
    't': ["true"]
}

cpp_builtin = {
    'a': ["auto_ptr", "abort", "abs", "acos", "asin", "atan2", "atan", "array"],
    'b': ["bitset"],
    'c': ["cin", "cout", "cerr", "clog", "complex"],
    'd': ["deque"],
    'e': ["endl", "exp", "exit"],
    'f': ["future", "fabs", "floor", "fmod", "fprintf", "fputs", "free", "frexp", "fscanf"],
    'i': ["istringstream", "initializer_list"],
    'l': ["list", "labs", "ldexp", "log10", "log"],
    'm': ["map", "multiset", "multimap", "main", "malloc", "memchr", "memcmp", "memcpy", "memset", "modf"],
    'o': ["ostringstream"],
    'p': ["pow", "printf", "putchar", "puts"],
    'q': ["queue"],
    's': ["std", "string", "string_view", "stringstream", "stdin", "stdout", "stderr", "set", "shared_ptr", "stack", "scanf", "sin", "sinh", "sqrt", "snprintf", "sprintf", "strcat", "strchr", "strcmp", "strcpy", "strcspn", "strlen", "strncat", "strncmp", "strncpy", "strpbrk", "strrchr", "strspn", "strstr", "tanh", "tan", "vfprintf", "vprintf", "vsprintf"],
    't': ["terminate"],
    'u': ["unordered_set", "unordered_map", "unordered_multiset", "unordered_multimap", "unique_ptr"],
    'v': ["vector"],
    'w': ["wstring"],
}

cpp_other = {
    'd': ["define"],
    'e': ["else", "elif", "endif", "error"],
    'i': ["if", "ifdef", "ifndef", "include"],
    'l': ["line"],
    'p': ["pragma"],
    'P': ["_Pragma"],
    'u': ["undef"],
    'w': ["warning"],
}


# C# language definitions

# C# keywords - organized by first letter
csharp_keywords = {
    'a': ["abstract", "add", "alias", "as", "ascending", "async", "await"],
    'b': ["base", "break"],
    'c': ["case", "catch", "checked", "const", "continue"],
    'd': ["decimal", "default", "delegate", "descending", "do", "dynamic"],
    'e': ["else", "event", "explicit", "extern"],
    'f': ["finally", "fixed", "for", "foreach", "from"],
    'g': ["get", "global", "goto", "group"],
    'i': ["if", "implicit", "in", "interface", "internal", "into", "is"],
    'j': ["join"],
    'l': ["let", "lock", "long"],
    'n': ["namespace", "new"],
    'o': ["object", "operator", "orderby", "out", "override"],
    'p': ["params", "partial", "private", "protected", "public"],
    'r': ["readonly", "ref", "remove", "return"],
    's': ["sealed", "select", "set", "sizeof", "stackalloc", "static", "switch"],
    't': ["this", "throw", "try", "typeof"],
    'u': ["unchecked", "unsafe", "using"],
    'v': ["value", "virtual", "volatile"],
    'w': ["where", "while"],
    'y': ["yield"]
}

# C# types
csharp_types = {
    'b': ["bool", "byte"],
    'c': ["char", "class"],
    'd': ["double"],
    'e': ["enum"],
    'f': ["float"],
    'i': ["int"],
    's': ["sbyte", "short", "string", "struct"],
    'u': ["uint", "ulong", "ushort"],
    'v': ["var", "void"]
}

# C# literals
csharp_literals = {
    'f': ["false"],
    't': ["true"],
    'n': ["null"]
}

# C# built-in types/functions (empty in original)
csharp_builtin = {}

# C# other elements (preprocessor directives, etc.)
csharp_other = {
    'd': ["define"],
    'e': ["elif", "else", "endif", "endregion", "error"],
    'i': ["if"],
    'l': ["line"],
    'p': ["pragma"],
    'r': ["region"],
    'u': ["undef"],
    'w': ["warning"]
}

# Python keywords organized by first letter
py_keywords = {
    'a': {"and", "as", "assert", "async", "await"},
    'b': {"break"},
    'c': {"class", "continue"},
    'd': {"def", "del"},
    'e': {"elif", "else", "except", "exec"},
    'f': {"from", "for", "finally"},
    'g': {"global"},
    'i': {"is", "in", "if"},
    'l': {"lambda"},
    'n': {"not", "nonlocal"},
    'o': {"or"},
    'p': {"print", "pass"},
    'r': {"raise", "return"},
    # self is not really a keyword, but it's used as a convention in Python
    's': {"self"},
    't': {"try"},
    'w': {"with", "while"},
    'y': {"yield"}
}

# Python types (empty in original)
py_types = {}

# Python literals
py_literals = {
    'F': {"False"},
    'T': {"True"},
    'N': {"None"}
}

# Python built-in functions
py_builtin = {
    '_': {"__import__"},
    'a': {"abs", "all", "any", "apply", "ascii"},
    'b': {"basestring", "bin", "bool", "buffer", "bytearray", "bytes"},
    'c': {"callable", "chr", "classmethod", "cmp", "coerce", "compile", "complex"},
    'd': {"delattr", "dict", "dir", "divmod"},
    'e': {"enumerate", "eval", "execfile"},
    'f': {"file", "filter", "float", "format", "frozenset"},
    'g': {"getattr", "globals"},
    'h': {"hasattr", "hash", "help", "hex"},
    'i': {"id", "input", "int", "intern", "isinstance", "issubclass", "iter"},
    'l': {"len", "list", "locals", "long"},
    'm': {"map", "max", "memoryview", "min"},
    'n': {"next"},
    'o': {"object", "oct", "open", "ord"},
    'p': {"pow", "property"},
    'r': {"range", "raw_input", "reduce", "reload", "repr", "reversed", "round"},
    's': {"set", "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super"},
    't': {"tuple", "type"},
    'u': {"unichr", "unicode"},
    'v': {"vars"},
    'x': {"xrange"},
    'z': {"zip"}
}

# Python other keywords
py_other = {
    'i': {"import"}
}


# Define the shell keywords as a dictionary with lists
shell_keywords = {
    'B': ["Bash"],
    'c': ["case"],
    'd': ["do", "done"],
    'e': ["else", "elif"],
    'f': ["fi", "for"],
    'i': ["if"],
    't': ["then"],
    'w': ["while"],
}

# Define shell types as an empty dictionary
shell_types = {}

# Define shell literals
shell_literals = {
    'f': ["false"],
    't': ["true"]
}

# Define shell built-in commands
shell_builtin = {
    'b': ["break"],
    'c': ["cd", "continue", "caller", "command", "cap", "chdir", "clone", "comparguments", "compcall", "compctl", "compdescribe", "compfilescompgroups", "compquote", "comptags", "comptry", "compvalues", "curl"],
    'd': ["docker"],
    'e': ["eval", "exec", "exit", "export", "echotc", "echoti", "emulatefc", "echo", "enable", "help"],
    'f': ["fg", "float", "functions", "fdisk", "flatpak"],
    'g': ["getopts", "git", "getcap", "getln"],
    'h': ["hash", "history", "help"],
    'i': ["integer"],
    'j': ["jobs"],
    'k': ["kill", "killall"],
    'l': ["let", "local", "logout", "limit", "log", "ls"],
    'm': ["mapfile", "mount", "mkdir", "mkswap", "modifiers"],
    'n': ["noglob", "nmcli"],
    'o': ["openssl"],
    'p': ["pwd", "printfread", "popd", "printpushd", "pushln", "pacman", "pamac", "php", "python", "perl"],
    'q': ["qownnotes"],
    'r': ["readonly", "return", "rehash", "readarray", "rm"],
    's': ["shift", "source", "set", "shopt", "sched", "setcap", "setopt", "stat", "suspend", "snap", "sudo"],
    't': ["test", "timestrap", "ttyctl"],
    'u': ["umask", "unset", "unfunction", "unhash", "unlimitunsetopt", "unalias"],
    'v': ["vared"],
    'w': ["wait", "whence", "where", "which", "wget"],
    'z': ["zcompile", "zformat", "zftp", "zle", "zmodload", "zparseopts", "zprof", "zpty", "zregexparse", "zsocket", "zstyle", "ztcp"],
    'y': ["yaourt"],
    'Q': ["QOwnNotes"],
}

# Define shell other as an empty dictionary
shell_other = {}


js_keywords = {
    'a': ["as", "async", "await", "arguments"],
    'b': ["break", "boolean"],
    'c': ["catch", "case", "continue", "class", "const", "console"],
    'd': ["do", "default", "debugger"],
    'e': ["else", "export"],
    'f': ["for", "finally", "function", "from"],
    'i': ["in", "if", "instanceof", "import"],
    'l': ["let", "long"],
    'n': ["new"],
    'o': ["of"],
    'r': ["return"],
    's': ["switch", "super", "static"],
    't': ["throw", "try", "this", "typeof"],
    'v': ["void"],
    'w': ["while", "with"],
    'y': ["yield"],
}

js_types = {
    'b': ["byte", "boolean"],
    'c': ["class"],
    'd': ["double"],
    'e': ["enum"],
    'f': ["float"],
    'i': ["int"],
    'l': ["long"],
    's': ["short"],
    'v': ["var", "void"],
}

js_literals = {
    'f': ["false"],
    'n': ["null"],
    't': ["true"],
    'u': ["undefined"],
    'N': ["NaN"],
    'I': ["Infinity"],
}

js_builtin = {
    'a': ["arguments"],
    'A': ["Array", "ArrayBuffer"],
    'B': ["Boolean"],
    'D': ["DataView", "Date"],
    'd': ["decodeURI", "decodeURIComponent", "document"],
    'e': ["eval", "encodeURI", "encodeURIComponent", "escape"],
    'E': ["Error", "EvalError"],
    'F': ["Function", "Float32Array", "Float64Array"],
    'i': ["isFinite", "isNaN"],
    'I': ["InternalError", "Int16Array", "Int32Array", "Int8Array", "Intl"],
    'J': ["JSON"],
    'm': ["module"],
    'O': ["Object"],
    'p': ["parseFloat", "parseInt"],
    'P': ["Proxy", "Promise"],
    'u': ["unescape"],
    'R': ["RangeError", "ReferenceError", "RegExp", "Reflect"],
    'r': ["require"],
    'S': ["StopIteration", "SyntaxError", "String", "Symbol", "Set"],
    'T': ["TypeError"],
    'U': ["URIError", "Uint16Array", "Uint32Array", "Uint8Array", "Uint8ClampedArray"],
    'w': ["window"],
    'W': ["WeakSet", "WeakMap"],
}

js_other = {}


java_keywords = {
    'a': ["abstract", "assert"],
    'b': ["break"],
    'c': ["case", "catch", "const", "continue"],
    'd': ["default", "do"],
    'e': ["else", "exports", "extends"],
    'f': ["final", "finally", "for"],
    'g': ["goto"],
    'i': ["if", "implements", "import", "instanceof", "interface"],
    'l': ["long"],
    'm': ["module"],
    'n': ["native", "new", "null"],
    'o': ["open", "opens"],
    'p': ["package", "private", "protected", "provides", "public"],
    'r': ["requires", "return"],
    's': ["static", "strictfp", "super", "switch", "synchronized"],
    't': ["this", "throw", "throws", "to", "transient", "transitive", "try"],
    'u': ["uses"],
    'v': ["var", "volatile"],
    'w': ["while", "with"],
    'y': ["yield"]
}

java_types = {
    'b': ["boolean", "byte"],
    'c': ["char", "class"],
    'd': ["double"],
    'e': ["enum"],
    'f': ["float"],
    'i': ["int"],
    's': ["short"],
    'v': ["void"],
}

java_literals = {
    'f': ["false"],
    't': ["true"]
}

java_builtin = {}
java_other = {}


def loadCppData():
    return cpp_types, cpp_keywords, cpp_builtin, cpp_literals, cpp_other


def loadJSData():
    return js_types, js_keywords, js_builtin, js_literals, js_other


def loadShellData():
    return shell_types, shell_keywords, shell_builtin, shell_literals, shell_other


def loadPHPData():
    return {}, {}, {}, {}, {}


def loadQMLData():
    return {}, {}, {}, {}, {}


def loadPythonData():
    return py_types, py_keywords, py_builtin, py_literals, py_other


def loadRustData():
    return {}, {}, {}, {}, {}


def loadJavaData():
    return java_types, java_keywords, java_builtin, java_literals, java_other


def loadCSharpData():
    return csharp_types, csharp_keywords, csharp_builtin, csharp_literals, csharp_other


def loadGoData():
    return {}, {}, {}, {}, {}


def loadVData():
    return {}, {}, {}, {}, {}


def loadSQLData():
    return {}, {}, {}, {}, {}


def loadJSONData():
    return {}, {}, {}, {}, {}


def loadCSSData():
    return {}, {}, {}, {}, {}


def loadTypeScriptData():
    return {}, {}, {}, {}, {}


def loadVexData():
    return {}, {}, {}, {}, {}


def loadCMakeData():
    return {}, {}, {}, {}, {}


def loadMakeData():
    return {}, {}, {}, {}, {}


def loadYAMLData():
    return {}, {}, {}, {}, {}


def loadNixData():
    return {}, {}, {}, {}, {}


def loadForthData():
    return {}, {}, {}, {}, {}


def loadSystemVerilogData():
    return {}, {}, {}, {}, {}


def loadGDScriptData():
    return {}, {}, {}, {}, {}


def loadTOMLData():
    return {}, {}, {}, {}, {}
