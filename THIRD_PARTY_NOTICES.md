# Third-Party Notices

noise-cut is released under the MIT License (see `LICENSE`). This file lists
the third-party components used by noise-cut and the licenses that apply to
them. Those components remain under their own licenses and are not covered by
the MIT License.

## Runtime dependencies

| Component | License | Source |
| --- | --- | --- |
| NumPy | BSD-3-Clause | https://numpy.org/ |
| python-sounddevice | MIT | https://github.com/spatialaudio/python-sounddevice |
| python-soxr (libsoxr) | LGPL-2.1-or-later | https://github.com/dofuuz/python-soxr |
| pystray | LGPL-3.0 | https://github.com/moses-palmer/pystray |
| Pillow | MIT-CMU | https://python-pillow.org/ |
| pynput | LGPL-3.0 | https://github.com/moses-palmer/pynput |
| deepfilternet-rs | MIT | https://github.com/di-osc/DeepFilterNet-rs |
| DeepFilterNet3 model | MIT OR Apache-2.0 (MIT selected) | https://github.com/Rikorose/DeepFilterNet |

Transitive Python dependencies include CFFI (MIT), pycparser (BSD-3-Clause),
six (MIT), jsonargparse (MIT), PyYAML (MIT), and typing_extensions (PSF-2.0).
Binary wheels of NumPy and Pillow may bundle additional libraries (for example
OpenBLAS, zlib, libjpeg-turbo); see their upstream license files for details.

## Bundled components

### RNNoise

`noisecut/rnnoise.dll` is part of RNNoise, Copyright (c) Xiph.Org Foundation
and contributors, licensed under the BSD-3-Clause license. The full license
text is included in `noisecut/RNNOISE_LICENSE.txt`.

Source: https://gitlab.xiph.org/xiph/rnnoise

### DeepFilterNet3 model

The DeepFilterNet3 ONNX model (`DeepFilterNet3_onnx.tar.gz`) is distributed
inside the deepfilternet-rs package, Copyright (c) DeepFilterNet contributors,
dual-licensed under MIT OR Apache-2.0. This project relies on the MIT option.

Source: https://github.com/Rikorose/DeepFilterNet

## VB-CABLE (not included)

VB-CABLE is proprietary donationware by Vincent Burel / VB-Audio, Copyright
(c) VB-Audio. All rights reserved. It is **not** part of this repository and is
**not** covered by the MIT License.

When the user chooses to install the virtual microphone, noise-cut downloads
the unmodified official package directly from VB-Audio:

- Origin: https://www.vb-cable.com
- Download: https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip
- Licensing: https://vb-audio.com/Services/licensing.htm

VB-CABLE is a donationware, all participations are welcome. Professional use
or distribution to organizations may require a paid license from VB-Audio.

## Build and runtime tools (binary releases)

| Component | License | Source |
| --- | --- | --- |
| Python | PSF-2.0 | https://docs.python.org/3/license.html |
| Tcl/Tk (tkinter) | BSD-style | https://www.tcl.tk/software/tcltk/license.html |
| PyInstaller | GPL-2.0-or-later with bootloader exception | https://pyinstaller.org/en/stable/license.html |

## LGPL compliance

soxr, pynput, and pystray are licensed under the LGPL. They are used as
separate, unmodified libraries. This repository contains the complete
application source code and the build scripts (`setup.bat`, `build.bat`) needed
to rebuild the binaries and to replace those libraries. Corresponding upstream
source code is available at the links above.

## Full license texts

- MIT: https://opensource.org/license/mit
- BSD-3-Clause: https://opensource.org/license/bsd-3-clause
- LGPL-2.1: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html
- LGPL-3.0: https://www.gnu.org/licenses/lgpl-3.0.html
- Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0
- PSF-2.0: https://docs.python.org/3/license.html
