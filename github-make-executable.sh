#!/bin/bash

make executable test-executable 2>&1 \
| while read -r line; do
  IFS=$'\n' read -r -a lines <<< "$line"
  if [[ "$line" == 'Nuitka'*':ERROR:'* ]]; then
    printf '::error file=codexctl.py,title=Nuitka Error::%s\n' "${lines[@]}"
  elif [[ "$line" == 'Nuitka'*':WARNING:'* ]]; then
    printf '::warning file=codexctl.py,title=Nuitka Warning::%s\n' "${lines[@]}"
  elif [[ "$line" == 'Nuitka:INFO:'* ]] || [[ "$line" == '[info]'* ]]; then
    echo "$line"
  else
    printf '::debug::%s\n' "${lines[@]}"
    echo "::debug::$line"
  fi
done
