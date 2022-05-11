#!/bin/bash
git status -s | sed "s/[[:space:]]/_/" | while read line;
do
	if [[ ${line:0:2} == "M_" ]] || [[ ${line:0:2} == "A_" ]]; then file=${line:3}; else continue; fi
        if [[ $file =~ \.py$ ]] ; then
                echo "Running for ${file}"
                black $file --target-version py38
                git add $file
        fi
done
