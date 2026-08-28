# Third-party notices

iCloud Live Photo Picker is licensed under GPL-3.0-or-later. The Windows portable package and Setup installer also contain third-party software under its own licenses.

| Component | Version | License / source |
| --- | --- | --- |
| PyQt6 | 6.10.2 | GPL-3.0 or Riverbank Commercial License; community wheels use GPL-3.0 |
| Qt 6 libraries shipped by PyQt6 | 6.10.x | LGPL-3.0/GPL-3.0/commercial, depending on the library |
| icloudpd / pyicloud_ipd | 1.32.3 | MIT; https://github.com/icloud-photos-downloader/icloud_photos_downloader |
| imageio-ffmpeg wrapper | 0.6.0 | BSD-2-Clause; https://github.com/imageio/imageio-ffmpeg |
| FFmpeg executable | 7.1 essentials build | GPLv3 build (`--enable-gpl --enable-version3`); https://ffmpeg.org/ and https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz |
| Pillow | 10.x–11.x | HPND; https://python-pillow.org/ |
| Inno Setup installer runtime | 7.1.0 | Inno Setup License; https://jrsoftware.org/ |

The pinned Python dependency set is recorded in `requirements.txt`. Copyright notices and exact license texts for individual Python distributions are available in their source distributions and installed `.dist-info/licenses` directories.

The FFmpeg executable is invoked as a separate process for optional MOV orientation compatibility. The packaged binary identifies itself as `ffmpeg 7.1-essentials_build-www.gyan.dev`; its configuration and version can be inspected with `ffmpeg -version`. FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project.

Apple, iCloud and Live Photo are trademarks of Apple Inc. This project is independent and is not endorsed by Apple.
