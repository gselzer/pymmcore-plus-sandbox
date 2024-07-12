# TODO Make something..nicer
pyinstaller .\src\pymmcore_plus_sandbox\__init__.py \
    --hidden-import ml_dtypes \
    --collect-all "cmap"