import os
import subprocess
import json
from pathlib import Path

FFPROBE = "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe"
FFMPEG = "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"

os.chdir("C:\Compress")


def run(args):
    print(f"[command] {args}")
    subprocess.run(args)


def capture(args):
    return subprocess.run(args, stdout=subprocess.PIPE, check=True).stdout


def probe(path):
    cmd = [
        FFPROBE,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        path,
    ]
    return json.loads(capture(cmd))


def is_h265(probe_json):
    return any(stream["codec_name"] == "h265" for stream in probe_json["streams"])


def convert(input_path, output_path, slice, resize_width, codec, crf):
    if output_path.is_file():
        print(f"Skipping: {output_path} exists")
        return
    working_path = output_path.with_suffix(".tmp.mp4")
    invocation = [FFMPEG, "-y", "-v", "quiet", "-stats", "-i", input_path]
    video = dict(
        av1_stv=["-c:v", "libsvtav1", "-cpu-used", "8"],
        av1_rav=["-c:v", "librav1e", "-cpu-used", "8"],
        av1=["-c:v", "libaom-av1", "-cpu-used", "8"],
        h265=["-c:v", "libx265", "-vtag", "hvc1"],
        copy=["-c:v", "copy"],
    )[codec]
    quality = ["-crf", str(crf)]
    resize = (
        ["-vf", f"scale={resize_width}:-1", "-sws_flags", "sinc"]
        if resize_width
        else []
    )
    slice = ["-ss", str(slice[0]), "-t", str(slice[1])] if slice else []
    audio = ["-c:a", "copy"]
    run(invocation + slice + resize + video + audio + quality + [working_path])
    os.rename(working_path, output_path)


def w_h_codec(probe_json):
    (stream,) = [s for s in probe_json["streams"] if s["codec_type"] == "video"]
    return stream["width"], stream["height"], stream["codec_name"]


def process_path(directory, slice=None, codec="h265", max_width=None, crf=20):
    sizes_path = sorted(
        ((p.stat().st_size, p) for p in directory.glob("*.mp4")), reverse=True
    )
    for index, (size, input_path) in enumerate(sizes_path, start=1):
        print(
            f"[{index}/{len(sizes_path)}] {input_path} is {size / 1024/1024/1024:.2f} GB"
        )
        if "h265" in str(input_path):
            print(f"  -  Skipping: The file is h265")
            continue
        if size < 1024 * 1024 * 1024:
            print(f"  -  Skipping: small file")
            continue
        width, height, input_codec = w_h_codec(probe(input_path))
        print(f"  -  Content probe : {width, height, input_codec}")
        if input_codec in ("h265", "hevc"):
            print(f"  -  Skipping: The file is h265")
            continue

        # output_path = input_path.with_stem(input_path.stem + "_copy")
        # convert(input_path, output_path, start=80, duration=10, codec="copy", crf=0)

        output_path = input_path.with_stem(input_path.stem + f"_{codec}_crf{crf}")
        resize_width = None
        if max_width and width > max_width:
            resize_width = max_width
            resize_height = height * max_width / width

            output_path = Path(
                str(output_path).replace(
                    f"{width}x{height}", f"{resize_width}x{resize_height}"
                )
            )
        if slice:
            output_path = output_path.with_stem(
                output_path.stem + f"_slice_{slice[0]}-{slice[1]}"
            )

        convert(
            input_path,
            output_path,
            slice=slice,
            resize_width=resize_width,
            codec=codec,
            crf=crf,
        )

        processed_original_file = output_path.parent / "original" / input_path.name
        os.makedirs(processed_original_file.parent, exist_ok=True)
        os.rename(input_path, processed_original_file)
        with open(processed_original_file.with_suffix(".bat"), "wt") as bat:
            bat.write(
                f"C:\\Compress\\GridPlayer\\GridPlayer.exe {processed_original_file} {output_path}\n"
            )
        with open(processed_original_file.parent / "report.txt", "at") as bat:
            bat.write(
                f"{output_path} {processed_original_file.stat().st_size / 1024 / 1024 / 1024:.2f} GiB -> {output_path.stat().st_size / 1024 / 1024 / 1024:.2f} GiB\n"
            )


dir_path = Path("W:\\")
process_path(dir_path, max_width=None, crf=18)
