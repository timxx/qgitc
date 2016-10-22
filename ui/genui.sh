#!/bin/bash

UIC_BIN=pyuic4

if ! which ${UIC_BIN} &> /dev/null ; then
    UIC_BIN=pyuic
fi

if ! which ${UIC_BIN} &> /dev/null ; then
    echo "Missing pyuic4, please setup the env or install it"
    exit -1
fi

cd "$( dirname "${BASH_SOURCE[0]}" )"

# cleaup old files
rm -f *.py

ui_files=`ls *.ui`

for file in ${ui_files} ; do
    ${UIC_BIN} ${file} -o ${file%.ui}.py
done
