#!/bin/bash

LUPDATE=pylupdate4

if [[ "$OS" =~ Windows* ]] ; then
    IFS=":" read -r -a _PATHS <<< $PATH
    for p in "${_PATHS[@]}" ; do
        if [[ "$p" == */Lib/site-packages/PyQt4 ]] ; then
            LUPDATE="${p}/pylupdate4.exe"
            break
        fi
    done
else
    if ! which ${LUPDATE} &> /dev/null ; then
        LUPDATE=pylupdate
    fi

    if ! which ${LUPDATE} &> /dev/null ; then
        echo "Missing pylupdate4, please setup the env or install it"
        exit -1
    fi
fi

cd "$( dirname "${BASH_SOURCE[0]}" )"
$LUPDATE gitc.pro
