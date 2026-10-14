#!/usr/bin/env bash
# Recovers the other participants' speech from a meeting whose Teams track was recorded at the wrong sample rate.
#
# Until 2026-10-14 teams-tap wrote the Teams track at the rate the tap reported (48 kHz) while the output
# device delivered fewer frames per second (16 kHz: a Bluetooth headset in a call). Every second it wrote
# 1/3 s of audio, 3x fast, and padded the rest with digital silence 0.2 s at a time. Only the mixed
# audio.m4a was kept, so this undoes it there. It strips the padding (silenceremove with peak detection
# over 5 ms windows, quieter than THRESHOLD for 0.01 s) and plays what is left at device/file speed
# (asetrate), which puts the remote speech back at its pitch and pace (judged intelligible by ear on
# 2026-10-14_15-38-49). The default 20 ms RMS detection kept most pads even of pure digital zeros: a 10 s
# tone gated 0.1 s on / 0.2 s off kept 5.2 s with it, 4.0 s with these settings, 3.3 s ideally.
#
# Limits: in the mix the pads are not digital silence, because the microphone track runs through them,
# so only some are stripped: 273 of the 475 s padded in 2026-10-14_15-38-49 (the output is 1311 s for a
# 710 s meeting), the remote speech in ~0.1 s bursts at the right speed, separated by quiet. A higher
# THRESHOLD (e.g. -60dB) strips more but starts eating quiet speech. The microphone half of the mix comes
# out slowed down, so use the result for the remote side only; its timestamps no longer match the
# meeting clock.
#
# Usage: [THRESHOLD=-70dB] scripts/recover-rate-mismatch.sh <meeting folder> [device rate] [file rate] [output]
#   device rate  default 16000 (the rate the output device really ran at)
#   file rate    default 48000 (the rate teams-tap wrote the Teams track at)
#   output       default <meeting folder>/audio.recovered.m4a
# Never touches audio.m4a, refuses to overwrite an existing output, and leaves nothing behind when it fails.
set -euo pipefail
DIR="${1:?usage: $0 <meeting folder> [device rate] [file rate] [output]}"
DEVICE_RATE="${2:-16000}"
FILE_RATE="${3:-48000}"
OUT="${4:-$DIR/audio.recovered.m4a}"
IN="$DIR/audio.m4a"
THRESHOLD="${THRESHOLD:--70dB}"
[ -f "$IN" ] || { echo "no audio.m4a in $DIR" >&2; exit 1; }
[ -e "$OUT" ] && { echo "already exists: $OUT (move it away first)" >&2; exit 1; }

RATE="$(ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate -of default=nw=1:nk=1 "$IN")"
# The mix kept the wrong time scale through its resampling to $RATE, so the fix is the same ratio at any rate.
SLOW_RATE=$(( RATE * DEVICE_RATE / FILE_RATE ))
echo "audio.m4a at $RATE Hz; stripping padding under $THRESHOLD and replaying at $SLOW_RATE Hz (device $DEVICE_RATE Hz, file $FILE_RATE Hz)"
# Written under a temporary name and renamed on success, so a failed run leaves nothing that blocks the next one.
PARTIAL="$(dirname "$OUT")/.$(basename "$OUT" .m4a).partial.m4a"
trap 'rm -f "$PARTIAL"' EXIT
ffmpeg -hide_banner -loglevel error -nostdin -y -i "$IN" \
  -af "silenceremove=stop_periods=-1:stop_duration=0.01:stop_threshold=${THRESHOLD}:detection=peak:window=0.005,asetrate=${SLOW_RATE},aresample=${RATE}" \
  -c:a aac -b:a 64k "$PARTIAL"
mv "$PARTIAL" "$OUT"
IN_S="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$IN")"
OUT_S="$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$OUT")"
printf 'wrote %s (%.0f s from %.0f s)\n' "$OUT" "$OUT_S" "$IN_S"
