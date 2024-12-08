#!/bin/bash
set +e

make executable 2>&1 \
| while read -r line; do
  IFS=$'\n' read -r -a lines <<< "$line"
  if [[ "$line" == 'Nuitka'*':ERROR:'* ]] || [[ "$line" == 'FATAL:'* ]] || [[ "$line" == 'make: *** ['*'] Error'* ]] ; then
    printf '::error file=main.py,title=Nuitka Error::%s\n' "${lines[@]}"
  elif [[ "$line" == 'Nuitka'*':WARNING:'* ]]; then
    printf '::warning file=main.py,title=Nuitka Warning::%s\n' "${lines[@]}"
  elif [[ "$line" == 'Nuitka:INFO:'* ]] || [[ "$line" == '[info]'* ]]; then
    echo "$line"
  else
    printf '::debug::%s\n' "${lines[@]}"
  fi
done

if ! make test-executable; then
  printf '::error file=codexctl,title=Test Error::Sanity test failed\n'
  exit 1
fi
