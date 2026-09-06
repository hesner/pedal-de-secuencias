# Library USB — folder and file naming

How to organize the library USB drive so `Library.resolve()`
(`src/core/library.py`) actually finds what you put on it. This isn't
enforced by any tool -- get a name wrong and the track is silently
treated as an empty slot (no error, nothing plays when the footswitch is
pressed). Read this before editing the library, not after a show goes
wrong.

## Structure

```
<USB root>/
├── active_show.txt          -- plain text, one line: the active show's folder name
├── standby.mp4               -- looped when nothing is playing
└── <Show Name>/               -- e.g. "Live", one folder per show/setlist collection
    ├── Set 1/
    │   ├── A - song name.mp3
    │   ├── B - another song.mp4
    │   └── C - a third one.wav
    ├── Set 2/
    │   └── ...
    └── Set N/
```

- **`active_show.txt`**: its content (trimmed) must exactly match a
  folder name directly under the USB root. If it points to a folder
  that doesn't exist, or is empty/unreadable, the standby fallback plays
  instead of any real content.
- **`Set N/`**: `N` is the setlist number, matching the controller group
  (see `MAVAVE_ANALYSIS.md` for how a group number maps to `N` for the
  M-VAVE PD41 specifically). Folder names are matched exactly as `Set `
  followed by digits -- `Set 1`, `Set 12`, not `set 1`, `Set1`, or `Set 01`.
- **Track files**: exactly one file per letter, `A`/`B`/`C` (footswitch
  `D` is always STOP -- it never needs a file). An empty slot (no file
  for a letter) is normal and expected, not an error.

## The one rule that actually matters: the filename pattern

```
<Letter> - <anything>.<extension>
```

**Exactly one space before the dash, one space after it.** The letter
must be immediately followed by ` - ` (space, dash, space), then any
name, then a supported extension:

- Audio-only (loops standby underneath, audio plays over it): `.mp3`, `.wav`
- Video with embedded audio: `.mp4`, `.mov`, `.mpeg`, `.mpg`

Case doesn't matter for the letter or the extension (`a - x.MOV` matches
fine). The only thing that has to be exact is that single space on each
side of the dash.

**This is the single easiest mistake to make**, and it fails completely
silently -- no error anywhere, the footswitch just does nothing, because
an unmatched filename looks identical to an intentionally empty slot.

```
A - my song.mp3        <- correct
A  - my song.mp3       <- WRONG (two spaces before the dash) -- silently ignored
A- my song.mp3         <- WRONG (no space before the dash) -- silently ignored
A -my song.mp3         <- WRONG (no space after the dash) -- silently ignored
```

**Safest way to avoid this**: don't type a new filename from scratch.
Duplicate an existing, already-working track file in the same or another
`Set` folder and rename only the part after ` - `, so the ` - ` itself
is never retyped.

If a track won't play and everything else looks right (file is really
there, right `Set` folder, right show active), rename the file to
double-check spacing first before assuming it's a codec or hardware
problem.

## Recommended encoding for phone-sourced video

`Set` folder videos are decoded in hardware (`mpv --hwdec=v4l2m2m-copy`
on the Raspberry Pi 2), which only supports **H.264**. Camera apps --
especially iPhone's -- default to settings this hardware can't touch at
all. Before copying phone footage into the library, re-encode it to:

| Setting | Recommended | Why |
|---|---|---|
| Video codec | H.264 (`libx264`) | The only codec this hardware decodes; `MASTER_SPECIFICATION.md`'s "Video" row |
| Pixel format | `yuv420p` (8-bit) | Phone HEVC/HDR footage is often 10-bit; the hardware decoder expects plain 8-bit 4:2:0 |
| Resolution | 1080p max (`scale=-2:1080`) | This project's target output resolution; 4K just adds decode work for no visible gain on an HDMI TV fed 1080p |
| Video bitrate | ~8-12 Mbps for 1080p | Comfortably good quality for a short clip. This is **not** the standby video's situation (`scripts/generate_fallback_standby.sh`'s output and the real `standby.mp4` are both encoded far leaner, around 1.8 Mbps) -- standby loops for the entire show and its file size actually matters; an individual song/video clip on the library USB doesn't have that constraint, so there's no reason to starve it on bitrate too |
| Audio codec | AAC, 44.1 or 48kHz, stereo | `Player` re-forces 48kHz/stereo on output regardless of the source, so the source just needs to be a normal AAC stream, not a specific sample rate |
| Container | `.mp4` | Regardless of the source's original extension -- a `.mov` input encodes to a `.mp4` output fine |

```
ffmpeg -i input.mov -c:v libx264 -pix_fmt yuv420p -vf scale=-2:1080 \
       -b:v 10M -c:a aac -b:a 192k -movflags +faststart "A - song name.mp4"
```

If a video plays fine on a phone/computer but not through the pedal,
check its codec (`ffmpeg -i <file>` shows it on the `Video:` line)
before suspecting the filename, and re-encode with the command above --
a wrong filename and the wrong codec can both be true of the same file
at once, so fixing one doesn't guarantee the other isn't also a problem.
