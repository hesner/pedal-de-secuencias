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
It has already happened once during this project's own testing: a file
named `A  - IMG_0896.MOV` (two spaces before the dash, easy to type by
accident) didn't play, with nothing in the log to explain why beyond
"no file for track A (empty slot)".

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

## Video codec note

`Set` folder videos are decoded in hardware (`mpv --hwdec=v4l2m2m-copy`
on the Raspberry Pi 2), which supports **H.264** -- the codec named in
`MASTER_SPECIFICATION.md`. A `.mov` file straight off an iPhone is often
**HEVC/H.265** instead of H.264 (depends on the camera's "Formats"
setting under iOS Settings → Camera), which this hardware decode path
does not support. If a video plays fine on a phone/computer but not
through the pedal, check its codec (`ffmpeg -i <file>` shows it on the
`Video:` line) before suspecting the filename.

The double-space example above actually happened together with exactly
this: the same file, once the filename is fixed, still won't play,
because `ffmpeg -i` shows it's `hevc (Main 10) ... 3840x2160, 59.94 fps`
-- 4K, 10-bit, HEVC, 60fps. Every part of that is past what this
hardware can decode (H.264 is the only hardware-decoded codec, and even
in software, 4K 10-bit HEVC has no realistic chance of keeping up on a
Pi 2). **Re-encode before copying to the library**, not just rename:

```
ffmpeg -i input.mov -c:v libx264 -pix_fmt yuv420p -vf scale=-2:1080 \
       -c:a aac -b:a 192k -movflags +faststart "A - song name.mp4"
```

`-pix_fmt yuv420p` matters even more than usual here -- it's what drops
the 10-bit HDR down to the plain 8-bit format the hardware decoder
expects. `scale=-2:1080` caps it at 1080p (this project's target
resolution); drop that flag only if the source is already 1080p or
smaller. Output as `.mp4` directly under the right `<Letter> - name`
pattern, so this step also can't reintroduce the spacing mistake above.
