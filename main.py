# nuitka-project: --enable-plugin=pylint-warnings
# nuitka-project: --enable-plugin=upx
# nuitka-project: --warn-implicit-exceptions
# nuitka-project: --onefile
# nuitka-project: --lto=yes
# nuitka-project: --include-package=google
# nuitka-project: --noinclude-unittest-mode=allow
# nuitka-project: --nofollow-import-to=setuptools
# nuitka-project-if: {OS} =="Darwin":
#    nuitka-project: --onefile-tempdir-spec="{CACHE_DIR}/codexctl/{VERSION}"

from codexctl import main

if __name__ == "__main__":
    main()
