# PyMMCore-Plus Sandbox

This WIPPY repository houses a pure-Python user interface for [Micro-Manager](https://micro-manager.org/). It is built atop the components built within the [pymmcore-plus](https://pymmcore-plus.github.io/pymmcore-plus/) organization, which is itself built atop [pymmcore](https://github.com/micro-manager/pymmcore).

This project is currently not intended to become a stable, distributable application, but is more devised as a proof-of-concept, showing that the widgets of [pymmcore-widgets](https://github.com/pymmcore-plus/pymmcore-widgets) are flexible enough to create a functional GUI with stark visual differences from the similar projects listed below. It was also fun!

# Other similar projects

## [napari-micromanager](https://github.com/pymmcore-plus/napari-micromanager)

This plugin for [napari](https://napari.org) provides a pure-Python user interface for micro-manager, directing output data to the napari viewer. Notably, compared to napari-micromanager, this UI:
* Imposes a smaller dependency stack
* Better handles changing datasets (for example, if you have a growing dataset, napari requires pre-existing knowledge of the total dataset size - otherwise, you'll have to reset the layer data on each frame being ready).
* enables "better" slider control i.e. through the display of  multiple sliders at once.
* (will) display within Jupyter

## [micromanager-gui](https://github.com/fdrgsp/micromanager-gui)

This UI is built atop similar technologies - the main difference is that this UI is designed to mimic the UI of [mmstudio](https://github.com/micro-manager/micro-manager/tree/main/mmstudio), the Java user interface for Micro-Manager that is used within ImageJ. This GUI, and that one, will likely be refined into a unified UI sometime in the future. See [pymmcore-gui](https://github.com/pymmcore-plus/pymmcore-gui) for efforts on that front!