# OMRChecker GUI

The desktop interface is a separate front end for the existing OMRChecker CLI. It calls the same processing entry point and accepts multiple input folders, an output folder, automatic alignment, template layout preview, and detailed tracebacks.

## Run

From the repository root, with the project dependencies installed:

```powershell
python GUI/main.py
```

The default input and output folders are `inputs` and `outputs`. Each input folder should contain the same template, configuration, evaluation, and scan files used by the CLI. Template layout preview uses the existing OpenCV image windows; press `Q` or `Esc` in each preview to continue.