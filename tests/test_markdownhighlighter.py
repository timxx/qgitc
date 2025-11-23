
from PySide6.QtWidgets import QPlainTextEdit

from qgitc.markdownhighlighter import MarkdownHighlighter, isValidEmail
from tests.base import TestBase


class TestMarkdownHighlighter(TestBase):
    def setUp(self):
        super().setUp()
        self.edit = QPlainTextEdit()
        self.highlighter = MarkdownHighlighter(self.edit.document())

    def doCreateRepo(self):
        pass

    def testSqlHighlighter(self):
        try:
            self.highlighter.sqlHighlighter("-")
        except IndexError as e:
            self.fail(f"Index out of range: {e}")

    def testTomlHighlighter(self):
        self.edit.setPlainText('```TOML\n[project]\nname = "qgitc"\n```')

    def testIsValidEmail(self):
        # Valid emails
        self.assertTrue(isValidEmail("test@example.com"))
        self.assertTrue(isValidEmail("user.name@domain.com"))
        self.assertTrue(isValidEmail("user-name@domain.co.uk"))

        # Invalid emails
        self.assertFalse(isValidEmail(""))
        self.assertFalse(isValidEmail("test"))
        self.assertFalse(isValidEmail("test@"))
        self.assertFalse(isValidEmail("@example.com"))
        self.assertFalse(isValidEmail("test@example"))
        self.assertFalse(isValidEmail("test..name@example.com"))

    def _test_language_highlighting(self, language, code, description=""):
        """Helper method to test language highlighting"""
        markdown_text = f"```{language}\n{code}\n```"

        # Just ensure no exceptions are thrown during highlighting
        try:
            self.edit.setPlainText(markdown_text)
        except Exception as e:
            self.fail(
                f"Language highlighting for {language} failed{' (' + description + ')' if description else ''}: {e}")

    def test_cpp_highlighting(self):
        """Test C++ syntax highlighting"""
        cpp_code = """
#include <iostream>
// comment
int main() {
    std::cout << "Hello World" << std::endl;
    return 0;
}
"""
        self._test_language_highlighting("cpp", cpp_code)
        self._test_language_highlighting("c++", cpp_code)
        self._test_language_highlighting("cxx", cpp_code)

    def test_c_highlighting(self):
        """Test C syntax highlighting"""
        c_code = """
#include <stdio.h>
int main() {
    printf("Hello World\\n");
    return 0;
}
"""
        self._test_language_highlighting("c", c_code)

    def test_python_highlighting(self):
        """Test Python syntax highlighting"""
        python_code = """
def hello_world():
    print("Hello, World!")
    return True

if __name__ == "__main__":
    hello_world()
"""
        self._test_language_highlighting("python", python_code)
        self._test_language_highlighting("py", python_code)

    def test_javascript_highlighting(self):
        """Test JavaScript syntax highlighting"""
        js_code = """
function helloWorld() {
    console.log("Hello, World!");
    return true;
}

const result = helloWorld();
"""
        self._test_language_highlighting("javascript", js_code)
        self._test_language_highlighting("js", js_code)

    def test_java_highlighting(self):
        """Test Java syntax highlighting"""
        java_code = """
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
"""
        self._test_language_highlighting("java", java_code)

    def test_csharp_highlighting(self):
        """Test C# syntax highlighting"""
        csharp_code = """
using System;

public class HelloWorld {
    public static void Main(string[] args) {
        Console.WriteLine("Hello, World!");
    }
}
"""
        self._test_language_highlighting("c#", csharp_code)
        self._test_language_highlighting("csharp", csharp_code)

    def test_go_highlighting(self):
        """Test Go syntax highlighting"""
        go_code = """
package main

import "fmt"

func main() {
    fmt.Println("Hello, World!")
}
"""
        self._test_language_highlighting("go", go_code)

    def test_rust_highlighting(self):
        """Test Rust syntax highlighting"""
        rust_code = """
fn main() {
    println!("Hello, World!");
}
"""
        self._test_language_highlighting("rust", rust_code)

    def test_php_highlighting(self):
        """Test PHP syntax highlighting"""
        php_code = """
<?php
echo "Hello, World!";
?>
"""
        self._test_language_highlighting("php", php_code)

    def test_swift_highlighting(self):
        """Test Swift syntax highlighting"""
        swift_code = """
import Foundation

// Hello World function

func helloWorld() {
    print("Hello, World!")
}

helloWorld()
"""
        self._test_language_highlighting("swift", swift_code)

    def test_objc_highlighting(self):
        """Test Objective-C syntax highlighting"""
        objc_code = """
#import <Foundation/Foundation.h>

@interface HelloWorld : NSObject
- (void)greet;
@end

@implementation HelloWorld
- (void)greet {
    NSLog(@"Hello, World!");
}
@end

int main() {
    NSLog(@"Hello, World!");
    return 0;
}
"""
        self._test_language_highlighting("objc", objc_code)
        self._test_language_highlighting("objective-c", objc_code)

    def test_bash_highlighting(self):
        """Test Bash syntax highlighting"""
        bash_code = """
#!/bin/bash
echo "Hello, World!"
for i in {1..5}; do
    echo "Number: $i"
done
"""
        self._test_language_highlighting("bash", bash_code)
        self._test_language_highlighting("sh", bash_code)

    def test_sql_highlighting(self):
        """Test SQL syntax highlighting"""
        sql_code = """
SELECT id, name, email 
FROM users 
WHERE active = 1 
ORDER BY name;
"""
        self._test_language_highlighting("sql", sql_code)

    def test_json_highlighting(self):
        """Test JSON syntax highlighting"""
        json_code = """
{
    "name": "qgitc",
    "version": "1.0.0",
    "dependencies": {
        "PySide6": "^6.0.0"
    }
}
"""
        self._test_language_highlighting("json", json_code)

    def test_xml_highlighting(self):
        """Test XML/HTML syntax highlighting"""
        xml_code = """
<?xml version="1.0" encoding="UTF-8"?>
<root>
    <item id="1">Hello World</item>
</root>
"""
        html_code = """
<!DOCTYPE html>
<html>
<head>
    <title>Hello World</title>
</head>
<body>
    <h1>Hello, World!</h1>
</body>
</html>
"""
        self._test_language_highlighting("xml", xml_code)
        self._test_language_highlighting("html", html_code)
        self._test_language_highlighting("svg", xml_code)

    def test_css_highlighting(self):
        """Test CSS syntax highlighting"""
        css_code = """
body {
    font-family: Arial, sans-serif;
    margin: 0;
    padding: 20px;
}

.header {
    color: #333;
    background-color: #f0f0f0;
    color: rgb(255, 255, 255);
    color: rgb(0, 0, 0);
}
"""
        self._test_language_highlighting("css", css_code)

    def test_typescript_highlighting(self):
        """Test TypeScript syntax highlighting"""
        ts_code = """
interface User {
    name: string;
    age: number;
}

function greetUser(user: User): string {
    return `Hello, ${user.name}!`;
}
"""
        self._test_language_highlighting("typescript", ts_code)
        self._test_language_highlighting("ts", ts_code)

    def test_yaml_highlighting(self):
        """Test YAML syntax highlighting"""
        yaml_code = """
name: qgitc
version: 1.0.0
dependencies:
  - PySide6
  - typing-extensions
scripts:
  start: python qgitc.py
http: https://example.com
# comment line
name: "string"
name: "aa
str: 'string'
str: 'aaa
"""
        self._test_language_highlighting("yaml", yaml_code)
        self._test_language_highlighting("yml", yaml_code)

    def test_toml_highlighting(self):
        """Test TOML syntax highlighting"""
        toml_code = """
[project]
name = "qgitc"
version = "1.0.0"
description = "Git client"
long-description = ''' \\
  long description here
  '''
not1 = nan
not2 = +nan
not3 = -nan
long-description = \"\"\" \\
  long description here
  \"\"\"

# comment

[project.dependencies]
PySide6 = "^6.0.0"
"""
        self._test_language_highlighting("toml", toml_code)

    def test_ini_highlighting(self):
        """Test INI syntax highlighting"""
        ini_code = """
[section1]
key1=value1
key2=value2

[section2]
option=true
wrong
=value;

; comment
[invalid section

"""
        self._test_language_highlighting("ini", ini_code)

    def test_cmake_highlighting(self):
        """Test CMake syntax highlighting"""
        cmake_code = """
cmake_minimum_required(VERSION 3.10)
project(HelloWorld)

add_executable(hello main.cpp)
target_link_libraries(hello ${CMAKE_REQUIRED_LIBRARIES})
"""
        self._test_language_highlighting("cmake", cmake_code)

    def test_makefile_highlighting(self):
        """Test Makefile syntax highlighting"""
        make_code = """
CC=gcc
CFLAGS=-Wall -g

all: hello

hello: main.o
	$(CC) -o hello main.o

main.o: main.c
	$(CC) $(CFLAGS) -c main.c

clean:
	rm -f *.o hello
"""
        self._test_language_highlighting("make", make_code)

    def test_nix_highlighting(self):
        """Test Nix syntax highlighting"""
        nix_code = """
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python3
    git
  ];
}
"""
        self._test_language_highlighting("nix", nix_code)

    def test_v_highlighting(self):
        """Test V language syntax highlighting"""
        v_code = """
fn main() {
    println('Hello, World!')
}
"""
        self._test_language_highlighting("v", v_code)

    def test_qml_highlighting(self):
        """Test QML syntax highlighting"""
        qml_code = """
import QtQuick 2.15
import QtQuick.Controls 2.15

ApplicationWindow {
    width: 640
    height: 480
    visible: true
    title: "Hello QML"

    Text {
        anchors.centerIn: parent
        text: "Hello, World!"
    }
}
"""
        self._test_language_highlighting("qml", qml_code)

    def test_vex_highlighting(self):
        """Test VEX syntax highlighting"""
        vex_code = """
vector pos = @P;
vector vel = {0, 1, 0};
@P = pos + vel * @TimeInc;
"""
        self._test_language_highlighting("vex", vex_code)

    def test_forth_highlighting(self):
        """Test Forth syntax highlighting"""
        forth_code = """
: hello ( -- )
    cr ." Hello, World!" cr ;

hello
"""
        self._test_language_highlighting("forth", forth_code)

    def test_systemverilog_highlighting(self):
        """Test SystemVerilog syntax highlighting"""
        sv_code = """
module hello_world;
    initial begin
        $display("Hello, World!");
        $finish;
    end
endmodule
"""
        self._test_language_highlighting("systemverilog", sv_code)

    def test_gdscript_highlighting(self):
        """Test GDScript syntax highlighting"""
        gdscript_code = """
extends Node

func _ready():
    print("Hello, World!")

func _process(delta):
    pass
"""
        self._test_language_highlighting("gdscript", gdscript_code)

    def test_taggerscript_highlighting(self):
        """Test TaggerScript syntax highlighting"""
        taggerscript_code = """
$set(album,"My Album")
$set(artist,"My Artist")
$if(%albumartist%,,$set(albumartist,%artist%))
$noop(comment)
$noop(bad
$set(foo, "escape \\char")
"""
        self._test_language_highlighting("taggerscript", taggerscript_code)

    def test_diff_highlighting(self):
        """Test Diff syntax highlighting"""
        diff_code = """
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 unchanged line
-removed line
+added line
++merge line
  > Submodule change
  < Submodule change2
 another unchanged line
"""
        self._test_language_highlighting("diff", diff_code)

    def test_unknown_language(self):
        """Test that unknown languages don't cause errors"""
        unknown_code = """
This is some generic code
with no specific syntax
"""
        self._test_language_highlighting(
            "unknown", unknown_code, "unknown language should not cause errors")

    def test_empty_code_blocks(self):
        """Test empty code blocks for all languages"""
        languages = ["cpp", "python", "javascript",
                     "java", "go", "rust", "sql"]
        for lang in languages:
            self._test_language_highlighting(
                lang, "", f"empty {lang} code block")

    def test_highlighting_special_characters(self):
        """Test highlighting with special characters"""
        special_code = """
# Comment with éspecial characters: áéíóú ñ
string = "String with unicode: ∑∞≈"
regex = r'[^\\w\\s]+'
"""
        self._test_language_highlighting(
            "python", special_code, "special characters")

    def test_nested_highlighting_structures(self):
        """Test complex nested structures"""
        complex_code = """
class MyClass {
    public void method() {
        if (condition) {
            for (int i = 0; i < 10; i++) {
                System.out.println("Value: " + i);
            }
        }
    }
}
"""
        self._test_language_highlighting(
            "java", complex_code, "nested structures")

    def test_syntax_highlighting_with_comments(self):
        """Test syntax highlighting with various comment styles"""
        # Test C++ style comments
        cpp_with_comments = """
// Single line comment
/* Multi-line
   comment */
int main() {
    return 0; // Another comment
}
"""
        self._test_language_highlighting(
            "cpp", cpp_with_comments, "C++ comments")

        # Test Python style comments
        python_with_comments = """
# This is a comment
def function():
    '''This is a docstring'''
    pass  # Inline comment
"""
        self._test_language_highlighting(
            "python", python_with_comments, "Python comments")

    def test_string_literals_highlighting(self):
        """Test string literal highlighting"""
        string_code = """
str1 = "Double quoted string"
str2 = 'Single quoted string'
str3 = '''Triple quoted string'''
str4 = "String with \\"escaped\\" quotes"
str5 = "String with \\n newline and \\t tab"
str6 = "Octal \\123 and hex \\xFF values"
"""
        self._test_language_highlighting(
            "python", string_code, "string literals")

    def test_string_escape_sequences(self):
        """Test string escape sequence highlighting"""
        escape_code = """
# Test various escape sequences
basic = "\\n\\t\\r\\\\\\'"
octal = "\\123\\777"
hex = "\\xFF\\x20"
unicode = "\\u1234"
"""
        self._test_language_highlighting(
            "python", escape_code, "escape sequences")

    def test_numeric_literals_highlighting(self):
        """Test numeric literal highlighting"""
        numeric_code = """
int_num = 42
float_num = 3.14159
hex_num = 0xFF
oct_num = 0o777
bin_num = 0b1010
scientific = 1.23e-4
"""
        self._test_language_highlighting(
            "python", numeric_code, "numeric literals")

    def test_edge_cases(self):
        """Test edge cases that might cause issues"""
        edge_cases = [
            ("", "completely empty"),
            ("    ", "only whitespace"),
            ("\n\n\n", "only newlines"),
            ("# ", "comment with space"),
            ("/**/", "empty C comment"),
            ('""', "empty string"),
            ("'", "single quote"),
            ('"', "double quote"),
            ("\\", "single backslash"),
        ]

        for code, description in edge_cases:
            self._test_language_highlighting(
                "python", code, f"edge case: {description}")

    def test_sql_multiline_comments(self):
        """Test SQL highlighting with multiline comments - regression test for bug fix"""
        sql_code = """
/* This is a multiline comment */
SELECT * FROM table;
-- This is a single line comment
SELECT id /* inline comment */ FROM users;
"""
        self._test_language_highlighting(
            "sql", sql_code, "SQL multiline comments")

    def test_sql_edge_cases(self):
        """Test SQL highlighter with edge cases that could cause IndexError"""
        edge_cases = [
            "-",  # Single dash - original test case
            "--",  # Double dash comment
            "/*",  # Start of multiline comment
            "*/",  # End of multiline comment
            "/* comment */",  # Complete multiline comment
            "SELECT * FROM table -- comment",  # Query with comment
        ]
        for case in edge_cases:
            self._test_language_highlighting(
                "sql", case, f"SQL edge case: {case}")

    def test_all_supported_languages_coverage(self):
        """Test that we have coverage for all officially supported languages"""
        # Get the language mapping from the highlighter
        MarkdownHighlighter.initCodeLangs()
        supported_languages = MarkdownHighlighter._langStringToEnum.keys()

        # Languages we have specific tests for
        tested_languages = {
            "bash", "sh", "c", "cpp", "c++", "cxx", "python", "py",
            "javascript", "js", "java", "c#", "csharp", "go", "rust",
            "php", "swift", "objc", "objective-c", "sql", "json",
            "xml", "html", "svg", "css", "typescript", "ts", "yaml",
            "yml", "toml", "ini", "cmake", "make", "nix", "v", "qml",
            "vex", "forth", "systemverilog", "gdscript", "taggerscript",
            "diff"
        }

        # Check that we test all supported languages
        untested = supported_languages - tested_languages
        if untested:
            self.fail(f"Untested languages found: {untested}")

    def test_language_case_sensitivity(self):
        """Test that language names are handled correctly regardless of case"""
        # The mapping should be case-insensitive ideally, but let's test current behavior
        test_code = "print('hello')"
        self._test_language_highlighting(
            "Python", test_code, "uppercase language name")
        self._test_language_highlighting(
            "PYTHON", test_code, "all caps language name")
        self._test_language_highlighting(
            "python", test_code, "lowercase language name")

    def _test_markdown_highlighting(self, markdown_text: str, description=""):
        """Helper method to test markdown highlighting"""
        # Set the text in the editor to trigger highlighting
        self.edit.setPlainText(markdown_text)

        # Just ensure no exceptions are thrown during highlighting
        try:
            lines = markdown_text.split('\n')
            for line in lines:
                self.highlighter.highlightBlock(line)
        except Exception as e:
            self.fail(
                f"Markdown highlighting failed{' (' + description + ')' if description else ''}: {e}")

    # ===== MARKDOWN FEATURE TESTS =====

    def test_headers_atx_style(self):
        """Test ATX-style headers (# ## ### etc.)"""
        header_text = """# Header 1
## Header 2
### Header 3
#### Header 4
##### Header 5
###### Header 6
####### Not a header (too many #)
"""
        self._test_markdown_highlighting(header_text, "ATX-style headers")

    def test_headers_setext_style(self):
        """Test Setext-style headers (underlined with = and -)"""
        header_text = """Header 1
========

Header 2
--------

Normal text that's not a header
Some more text
"""
        self._test_markdown_highlighting(header_text, "Setext-style headers")

    def test_headers_with_indentation(self):
        """Test headers with allowed indentation"""
        header_text = """   # Indented header (allowed up to 3 spaces)
  ## Another indented header
    # This should not be a header (4 spaces = code block)
"""
        self._test_markdown_highlighting(
            header_text, "headers with indentation")

    def test_unordered_lists(self):
        """Test unordered list highlighting"""
        list_text = """- Item 1
- Item 2
  - Nested item 2.1
  - Nested item 2.2
- Item 3

* Alternative bullet style
* Another item
  * Nested with asterisk

+ Plus sign bullets
+ Another plus item
  + Nested plus item
"""
        self._test_markdown_highlighting(list_text, "unordered lists")

    def test_ordered_lists(self):
        """Test ordered list highlighting"""
        list_text = """1. First item
2. Second item
   1. Nested item
   2. Another nested item
3. Third item

10. Starting from 10
11. Eleventh item

1) Parenthesis style
2) Another item
"""
        self._test_markdown_highlighting(list_text, "ordered lists")

    def test_checkboxes(self):
        """Test checkbox highlighting in task lists"""
        checkbox_text = """- [ ] Unchecked task
- [x] Checked task
- [X] Another checked task (capital X)
- [ ] Unchecked with description
- [x] Checked with description

1. [ ] Numbered unchecked task
2. [x] Numbered checked task
3. [ ] Another numbered task
"""
        self._test_markdown_highlighting(
            checkbox_text, "checkboxes in task lists")

    def test_emphasis_and_strong(self):
        """Test emphasis (italic) and strong (bold) text"""
        emphasis_text = """This is *italic text* with asterisks.
This is _italic text_ with underscores.

This is **bold text** with double asterisks.
This is __bold text__ with double underscores.

This is ***bold and italic*** text.
This is ___bold and italic___ text.

Mixed: *italic* and **bold** and ***both***.

Not emphasis: * single asterisk without closing
Not emphasis: ** double asterisk without closing

Escaped: \\*not italic\\* and \\**not bold\\**
"""
        self._test_markdown_highlighting(
            emphasis_text, "emphasis and strong text")

    def test_inline_code(self):
        """Test inline code spans"""
        code_text = """This is `inline code` in a sentence.

Code with `backticks` and more `code spans`.

Code with multiple backticks: ``code with ` backtick``.

Triple backticks: ```inline triple``` code.

Escaped: \\`not code\\`

Code at start: `var x = 1;` and at end.
"""
        self._test_markdown_highlighting(code_text, "inline code spans")

    def test_strikethrough(self):
        """Test strikethrough text"""
        strikethrough_text = """This is ~~strikethrough~~ text.

Multiple ~~strikethrough~~ ~~sections~~ in one line.

Mixed with *italic* and ~~strikethrough~~ and **bold**.

Not strikethrough: ~ single tilde
Not strikethrough: ~~~ triple tilde (this might be code fence)
"""
        self._test_markdown_highlighting(
            strikethrough_text, "strikethrough text")

    def test_blockquotes(self):
        """Test blockquote highlighting"""
        blockquote_text = """> This is a blockquote.
> It can span multiple lines.
> 
> > Nested blockquotes are possible.
> > Like this.

> Blockquote with **bold** and *italic* text.
> And `inline code` too.

Not a blockquote because no space:
>no space after >

    > Indented blockquote (should still work)
"""
        self._test_markdown_highlighting(blockquote_text, "blockquotes")

    def test_horizontal_rules(self):
        """Test horizontal rule highlighting"""
        hr_text = """Text before rule.

---

Text between rules.

***

More text.

___

Different styles of horizontal rules.

- - -

* * *

_ _ _

Not a rule: --
Not a rule: **
Not a rule: __
"""
        self._test_markdown_highlighting(hr_text, "horizontal rules")

    def test_links(self):
        """Test link highlighting"""
        link_text = """This is an [inline link](https://example.com).

This is a [link with title](https://example.com "Link Title").

Reference links: [link text][1] and [another link][ref].

[1]: https://example.com
[ref]: https://github.com "GitHub"

Automatic links: <https://example.com>
Email links: <user@example.com>

URLs: https://example.com
FTP: ftp://files.example.com

href="https://example.com"
href="badlink

<a href="">
<a bad
"""
        self._test_markdown_highlighting(link_text, "links")

    def test_images(self):
        """Test image highlighting"""
        image_text = """Inline image: ![Alt text](image.jpg)

Image with title: ![Alt text](image.jpg "Image Title")

Reference image: ![Alt text][img]

[img]: image.jpg "Reference Image"

Image with link: [![Alt text](image.jpg)](https://example.com)
"""
        self._test_markdown_highlighting(image_text, "images")

    def test_tables(self):
        """Test table highlighting"""
        table_text = """| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |

| Left | Center | Right |
|:-----|:------:|------:|
| L1   |   C1   |    R1 |
| L2   |   C2   |    R2 |

Simple table:
| Name | Age |
|------|-----|
| John | 25  |
| Jane | 30  |
"""
        self._test_markdown_highlighting(table_text, "tables")

    def test_code_blocks_fenced(self):
        """Test fenced code blocks"""
        code_text = """```
Plain code block
with multiple lines
```

```python
def hello():
    print("Hello, World!")
```

```javascript
function hello() {
    console.log("Hello, World!");
}
```

~~~
Alternative fence style
with tildes
~~~

```
Empty language specifier
```
"""
        self._test_markdown_highlighting(code_text, "fenced code blocks")

    def test_code_blocks_indented(self):
        """Test indented code blocks"""
        code_text = """Regular paragraph.

    This is a code block
    because it's indented
    with 4 spaces.

Regular paragraph again.

        More indented code
        with 8 spaces total.

Back to normal text.

	Tab-indented code block
	using tabs instead of spaces.
"""
        self._test_markdown_highlighting(code_text, "indented code blocks")

    def test_html_comments(self):
        """Test HTML comment highlighting"""
        comment_text = """<!-- This is an HTML comment -->

<!-- 
Multi-line
HTML comment
-->

Text with <!-- inline comment --> in the middle.

Nested: <!-- outer <!-- inner --> comment -->
"""
        self._test_markdown_highlighting(comment_text, "HTML comments")

    def test_markdown_comments(self):
        """Test markdown-style comments"""
        comment_text = """[//]: # (This is a markdown comment)
[comment]: # (Another comment style)
[//]: # "Comment with quotes"

Regular text here.

[//]: # (
Multi-line markdown comment
spanning several lines
)
"""
        self._test_markdown_highlighting(comment_text, "markdown comments")

    def test_frontmatter(self):
        """Test frontmatter block highlighting"""
        frontmatter_text = """---
title: Test Document
author: Test Author
date: 2023-10-27
tags: [test, markdown]
---

# Document Content

This is the actual document content after frontmatter.
"""
        self._test_markdown_highlighting(
            frontmatter_text, "frontmatter blocks")

    def test_mixed_markdown_features(self):
        """Test complex documents with mixed markdown features"""
        mixed_text = """# Main Title

This document contains **multiple** *markdown* features.

## Lists and Tasks

- [x] Completed task
- [ ] Incomplete task
- Regular list item with `inline code`

### Code Example

```python
def process_data(data):
    return [item.upper() for item in data]
```

> **Note**: This is a blockquote with **bold** text.
> It contains a [link](https://example.com) too.

## Table

| Feature | Status | Notes |
|---------|--------|-------|
| Headers | ✓      | Working |
| Lists   | ✓      | Working |
| Code    | ✓      | Working |

---

*End of document*
"""
        self._test_markdown_highlighting(mixed_text, "mixed markdown features")

    def test_edge_cases_markdown(self):
        """Test edge cases in markdown highlighting"""
        edge_cases = [
            ("# ", "header with only space"),
            ("## ", "h2 with only space"),
            ("- ", "list item with only space"),
            ("- [ ]", "checkbox without space after"),
            ("- [x]", "checked box without space after"),
            ("> ", "blockquote with only space"),
            ("---", "horizontal rule only"),
            ("```", "code fence only"),
            ("``", "double backticks"),
            ("`", "single backtick"),
            ("*", "single asterisk"),
            ("**", "double asterisk"),
            ("***", "triple asterisk"),
            ("_", "single underscore"),
            ("__", "double underscore"),
            ("___", "triple underscore"),
            ("~~", "double tilde"),
            ("| |", "empty table"),
            ("[]()", "empty link"),
            ("![]()", "empty image"),
            ("<!-- -->", "empty comment"),
        ]

        for markdown, description in edge_cases:
            self._test_markdown_highlighting(
                markdown, f"edge case: {description}")

    def test_markdown_escaping(self):
        """Test that escaped markdown characters are handled correctly"""
        escaped_text = """\\# Not a header
\\* Not a list item
\\** Not bold text
\\[Not a link\\](url)
\\`Not inline code\\`
\\> Not a blockquote
\\--- Not a horizontal rule

Backslash at end: text\\
Double backslash: text\\\\
"""
        self._test_markdown_highlighting(
            escaped_text, "escaped markdown characters")

    def test_trailing_spaces(self):
        """Test trailing space highlighting"""
        trailing_text = """Line with trailing spaces  
Another line with spaces   
Line without trailing spaces
Empty line with spaces:  

Normal line again.
"""
        self._test_markdown_highlighting(trailing_text, "trailing spaces")

    def test_markdown_with_unicode(self):
        """Test markdown with Unicode characters"""
        unicode_text = """# Ünïcødé Hëädér

- Ïtém with émojis 🎉 ✨
- [Liñk tö Ünicöde](https://example.com/ünïcødé)

**Böld téxt** with *ïtälïc* and `cödé` with ünïcødé.

> Blöckquöte with spéciäl chäräctérs: áéíóú ñ ç

| Näme | Ägé | Lócätïön |
|------|-----|----------|
| José | 25  | Spàïn    |
| Mönicä | 30  | Gérmanÿ |
"""
        self._test_markdown_highlighting(unicode_text, "Unicode characters")

    def test_nested_markdown_structures(self):
        """Test deeply nested markdown structures"""
        nested_text = """1. First level list
   - Second level bullet
     1. Third level numbered
        - Fourth level bullet
          > Fifth level blockquote
          > with **bold** and *italic*
          > and `inline code`

2. Another first level
   > Blockquote in list
   > with [link](https://example.com)
   > 
   > | Table | In Quote |
   > |-------|----------|
   > | Cell  | Value    |

3. List with code:
   ```python
   # Code in list
   def nested_function():
       return "nested"
   ```
"""
        self._test_markdown_highlighting(
            nested_text, "nested markdown structures")

    def test_malformed_markdown(self):
        """Test that malformed markdown doesn't cause crashes"""
        malformed_cases = [
            "# Unclosed emphasis *text",
            "**Unclosed bold text",
            "[Unclosed link(url)",
            "![Unclosed image(url)",
            "```\nUnclosed code block",
            "~~~\nUnclosed tilde block",
            "<!-- Unclosed comment",
            "- [ Malformed checkbox",
            "| Malformed | table",
            "> > > >>> Many blockquotes",
            "# # # ### Multiple hashes",
        ]

        for malformed in malformed_cases:
            self._test_markdown_highlighting(
                malformed, f"malformed: {malformed[:20]}...")

    def test_performance_large_document(self):
        """Test highlighting performance with a large document"""
        # Create a reasonably large document
        large_doc_parts = [
            "# Large Document Test\n",
            "This is a performance test with a large markdown document.\n\n",
        ]

        # Add many list items
        for i in range(100):
            large_doc_parts.append(
                f"- List item {i} with **bold** and *italic* text\n")

        # Add code blocks
        large_doc_parts.append("\n```python\n")
        for i in range(50):
            large_doc_parts.append(f"def function_{i}():\n    return {i}\n")
        large_doc_parts.append("```\n\n")

        # Add table
        large_doc_parts.append(
            "| Col1 | Col2 | Col3 |\n|------|------|------|\n")
        for i in range(50):
            large_doc_parts.append(f"| Row{i} | Data{i} | Value{i} |\n")

        large_text = "".join(large_doc_parts)
        self._test_markdown_highlighting(
            large_text, "large document performance test")

    def test_checkbox_variations(self):
        """Test various checkbox formats and edge cases"""
        checkbox_variations = """- [ ] Standard unchecked
- [x] Standard checked
- [X] Capital X checked
- [-] Dash checkbox (custom)
- [ ] Checkbox with trailing spaces  
- [x] Checked with trailing spaces  
- [  ] Extra space (malformed)
- [xx] Double x (malformed)
- [] Empty brackets (malformed)
- [ Missing closing bracket
- [ ] Checkbox with **bold** text after
- [x] Checked with *italic* and `code`

1. [ ] Numbered unchecked
2. [x] Numbered checked
3. [X] Numbered capital X

  - [ ] Indented unchecked
  - [x] Indented checked
    - [ ] Double indented
    - [x] Double indented checked
"""
        self._test_markdown_highlighting(
            checkbox_variations, "checkbox variations")

    def test_list_edge_cases(self):
        """Test edge cases in list highlighting"""
        list_edge_cases = """- Single item
-Missing space (malformed)
- 
- Empty item

1. Numbered item
1.Missing space (malformed)
10. Double digit
100. Triple digit
1000. Four digits (should work)
10000. Five digits (might not work as list)

* Asterisk list
*Missing space
** Double asterisk

+ Plus list
+Missing space
++ Double plus

-Not a list because not at start
 - Indented list (should work)
  - Double indented
   - Triple indented
    - Quad indented

- Mixed markers:
  * Asterisk under dash
  + Plus under dash
  1. Number under dash
"""
        self._test_markdown_highlighting(list_edge_cases, "list edge cases")

    def test_blockquote_edge_cases(self):
        """Test edge cases in blockquote highlighting"""
        blockquote_edge_cases = """> Standard blockquote
>Missing space (malformed)
> 
> Empty blockquote line

> > Nested blockquotes
> > > Triple nested
> > > > Quad nested

> Blockquote with `code` and **bold**
> 
> Multi-paragraph blockquote
> Second paragraph

> Blockquote
Regular text (not quoted)
> Another blockquote

    > Indented blockquote
  > Different indentation
 > Another indentation

> Quote with list:
> - Item 1
> - Item 2
> 
> Back to quote text
"""
        self._test_markdown_highlighting(
            blockquote_edge_cases, "blockquote edge cases")

    def test_code_block_edge_cases(self):
        """Test edge cases in code block highlighting"""
        code_edge_cases = """```
Basic code block
```

```python
Python code block
def hello():
    pass
```

```python```
Inline code fence (should be inline, not block)

```
Unclosed code block

~~~
Tilde code block
~~~

~~~python
Tilde with language
~~~

    Indented code block
    with multiple lines

Regular text

    Another indented block

Mix:
```
Fenced
```
    Indented
More regular text

````
Quad-backtick block
```
Triple inside quad
````
"""
        self._test_markdown_highlighting(
            code_edge_cases, "code block edge cases")

    def test_table_edge_cases(self):
        """Test edge cases in table highlighting"""
        table_edge_cases = """| Simple | Table |
|--------|-------|
| Cell1  | Cell2 |

|Minimal|Table|
|--|--|
|A|B|

| Spaced | Out | Table |
| ------ | --- | ----- |
| Cell   | X   | Y     |

|Missing ending pipe
|--|
|Cell|

| Header |
| ------ |
| Single column |

| No | Separators |
| Cell1 | Cell2 |

||Empty|Headers||
|--|--|--|--|
||Empty|Cells||

| Unicode | Tåblë |
|---------|-------|
| çéll    | dätá  |
"""
        self._test_markdown_highlighting(table_edge_cases, "table edge cases")

    def test_link_edge_cases(self):
        """Test edge cases in link highlighting"""
        link_edge_cases = """[Simple link](http://example.com)
[Link with title](http://example.com "Title")
[Link with 'single quotes'](http://example.com 'Title')

[Empty link]()
[](http://example.com)
[Missing URL](missing-scheme)

[Unclosed link](http://example.com
[Missing closing paren](http://example.com

Reference links:
[Ref link][ref]
[ref]: http://example.com

[Undefined ref][missing]

Auto links:
<http://example.com>
<user@example.com>
<ftp://files.example.com>
<invalid-email>

Raw URLs:
http://example.com
https://secure.example.com
ftp://files.example.com
Not a URL: ttp://missing-h.com

Nested links:
[![Image](img.jpg)](http://example.com)
[Link with **bold** text](http://example.com)
"""
        self._test_markdown_highlighting(link_edge_cases, "link edge cases")

    def test_emphasis_edge_cases(self):
        """Test edge cases in emphasis highlighting"""
        emphasis_edge_cases = """*Basic italic*
**Basic bold**
***Bold and italic***

Not emphasis: * * separate asterisks
Not emphasis: ** ** separate double

Nested: ***bold *italic* in bold***
Mixed: **bold *and italic* text**

Underscores: _italic_ and __bold__ and ___both___
Mixed markers: *italic* and __bold__

Not emphasis because of spaces: * space separated *
Not emphasis: ** double space **

Mid-word_emphasis_works
Mid-word*emphasis*works

Escaped: \\*not italic\\* and \\**not bold\\**

Multiple: *one* *two* *three*
Adjacent: **bold***italic*

Unclosed: *missing closing asterisk
Unclosed: **missing double closing

Symbol after: *italic*, **bold**.
Symbol before: (*italic*), [**bold**]

Unicode: *itálicas* **negritas** ***ambás***
"""
        self._test_markdown_highlighting(
            emphasis_edge_cases, "emphasis edge cases")

    def test_inline_code_edge_cases(self):
        """Test edge cases in inline code highlighting"""
        inline_code_edge_cases = """`Simple code`
``Code with ` backtick``
```Code with `` double backticks```

`Multiple` `code` `spans`
Adjacent`code`spans

Unclosed: `missing closing backtick
Empty: ``

Code with spaces: ` spaced code `
Code without spaces: `unspaced`

Escaped: \\`not code\\`

Code in other formatting:
**Bold with `code` inside**
*Italic with `code` inside*
[Link with `code`](http://example.com)

Code at boundaries:
Start with `code` and end.
Middle `code` span here.
End with text and `code`.

Special chars in code: `<>&"'`
Unicode in code: `ünïcødé`
"""
        self._test_markdown_highlighting(
            inline_code_edge_cases, "inline code edge cases")

    def test_comprehensive_markdown_document(self):
        """Test a comprehensive markdown document with all features"""
        comprehensive_doc = """# Comprehensive Markdown Test Document

This document tests **all** *major* markdown features together.

## Table of Contents

- [Headers](#headers)
- [Lists](#lists)
- [Code](#code)
- [Links](#links)

## Headers

### Subsection
#### Sub-subsection
##### Fifth level
###### Sixth level

Alternative syntax:
================

Second level alternative
------------------------

## Lists

### Unordered Lists

- Item 1 with **bold** text
  - Nested item with *italic*
  - Another nested item
    - Deep nesting with `code`
- [ ] Unchecked task
- [x] Completed task
- Item with [link](http://example.com)

### Ordered Lists

1. First item
2. Second item with **emphasis**
   1. Nested numbered
   2. Another nested
3. Third item

## Code

Inline `code` spans and blocks:

```python
def hello_world():
    print("Hello, World!")
    return True

# Comment
result = hello_world()
```

Indented code block:

    function() {
        return "indented";
    }

## Links and Images

Link: [GitHub](https://github.com)
Image: ![Alt text](image.jpg "Title")
Email: <user@example.com>
Auto-link: <https://example.com>

Reference style:
[Link text][ref1]
![Image][ref2]

[ref1]: https://example.com "Reference link"
[ref2]: image.jpg "Reference image"

## Quotes and Rules

> This is a blockquote with **bold** text.
> 
> > Nested quote with *italic* text.
> > And `inline code`.

---

Horizontal rule above.

## Tables

| Feature | Status | Notes |
|---------|--------|-------|
| Headers | ✓      | Working |
| Lists   | ✓      | All types |
| Code    | ✓      | Both inline and blocks |
| Links   | ✓      | All formats |
| Tables  | ✓      | This one! |

## Special Features

Strikethrough: ~~deleted text~~

Mix of everything: **Bold** with *italic* and `code` and [link](http://example.com) and ~~strikethrough~~.

<!-- This is an HTML comment -->

Trailing spaces test:  
Line break above.

---

*End of comprehensive test document.*
"""
        self._test_markdown_highlighting(
            comprehensive_doc, "comprehensive markdown document")
