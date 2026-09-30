# Third-party notices

CLA uses independently maintained components. Their licenses remain applicable regardless of CLA's pending source-license decision. Do not treat this overview as a replacement for the actual notices and license text shipped with a release.

Major runtime components include Python, the MCP Python SDK, Pydantic/pydantic-core, psutil, platformdirs, tomlkit, httpx and its dependencies, PyYAML, and optional PySide6/Shiboken/Qt. Build/test tools include Hatchling, build, PyInstaller and pytest-related packages. Transitive components are listed in the release dependency inventory.

The portable build includes a Python runtime and Qt libraries. It does not bundle Codex, PowerShell, Conda, Blender, Maxima, CUDA, PyTorch environments, models or personal configuration. Those independently installed products retain their own terms and notices.

The build process collects available installed distribution license metadata and license files into the portable third-party materials. Review the generated inventory and supplied texts for the exact component versions and applicable obligations. In particular, Qt/PySide licensing and any separately licensed Qt modules must be reviewed before broader redistribution. Keeping Qt libraries as separate files does not by itself establish complete license compliance.

CLA does not claim ownership of third-party trademarks, provide a commercial Qt license, certify a license audit, or override third-party redistribution obligations. Do not publish the private prerelease publicly until the licensing review and CLA licensing decision are complete.
