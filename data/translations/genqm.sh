#!/bin/bash

LRELEASE=lrelease-qt4

if [[ "$OS" =~ Windows* ]] ; then
    IFS=":" read -r -a _PATHS <<< $PATH
    for p in "${_PATHS[@]}" ; do
        if [[ "$p" == */Lib/site-packages/PyQt4 ]] ; then
            LRELEASE="${p}/lrelease.exe"
            break
        fi
    done
else
    if ! which ${LRELEASE} &> /dev/null ; then
        LRELEASE=lrelease
    fi

    if ! which ${LRELEASE} &> /dev/null ; then
        echo "Missing lrelease-qt4, please setup the env or install it"
        exit -1
    fi
fi

cd "$( dirname "${BASH_SOURCE[0]}" )"
${LRELEASE} gitc.pro
