#!/bin/bash

UIC_BIN=pyuic4

if [[ "$OS" =~ Windows* ]] ; then
    IFS=":" read -r -a _PATHS <<< $PATH
    for p in "${_PATHS[@]}" ; do
        if [[ "$p" == */Lib/site-packages/PyQt4 ]] ; then
            UIC_BIN="python ${p}/uic/pyuic.py"
            break
        fi
    done
else
    if ! which ${UIC_BIN} &> /dev/null ; then
    UIC_BIN=pyuic
    fi

    if ! which ${UIC_BIN} &> /dev/null ; then
        echo "Missing pyuic4, please setup the env or install it"
        exit -1
    fi
fi

cd "$( dirname "${BASH_SOURCE[0]}" )"

# cleaup old files
rm -f *.py

ui_files=`ls *.ui`

for file in ${ui_files} ; do
    ${UIC_BIN} ${file} -o ${file%.ui}.py
done
