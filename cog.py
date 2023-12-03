# Useful commands
#
# Make files available to transmission:
# sudo ln *.mp4 /var/lib/transmission-daemon/downloads
#
# List transmission torrents:
# transmission-remote -n transmission:transmission -l
import subprocess
import pathlib
import re
import json
import dataclasses
import sys
import os
import shutil

FFPROBE = "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe"
FFMPEG = "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe"
MEDIA_INFO = "mediainfo/MediaInfo.exe"
TRANSMISSION = "C:/Program Files/Transmission/transmission-create.exe"
typos = {
    "Doesnt": "Doesn't",
}


# Dataclass for video metadata
@dataclasses.dataclass
class VideoMetadata:
    """Dataclass for video metadata."""

    title: str
    actors: list[str]
    duration_sec: float
    width: int
    height: int
    fps: float
    video_codec: str
    video_bps: int
    audio_codec: str
    audio_bps: int
    file_size: int


def split_camel_case(s):
    """Split a camel case string into a list of strings."""
    return re.findall(r"[A-Z](?:[a-z]+|[A-Z]*(?=[A-Z]|$))", s)


def camel_case_to_space(s):
    """Convert a camel case string to a space separated string."""
    return " ".join(split_camel_case(s))


def capture(args):
    print(f"[Run]: {' '.join(str(a) for a in args)}")
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


def get_video_metadata(file):
    # Split file name on underscore, and drop the systematic last
    # 4 parts which is typically `_5568x3132_60fps_h265_crf21.mp4`
    parts = file.name.split("_")[:-4]
    title = camel_case_to_space(parts[-1])
    actors = [camel_case_to_space(a) for a in parts[:-1]]
    # Replace all typos with correct spelling
    for typo, correct in typos.items():
        title = title.replace(typo, correct)

    # Get video metadata
    video_data = probe(file)

    video_stream = next(s for s in video_data["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in video_data["streams"] if s["codec_type"] == "audio")
    num, demon = video_stream["r_frame_rate"].split("/")

    return VideoMetadata(
        title=title,
        actors=actors,
        duration_sec=round(float(video_stream["duration"])),
        width=int(video_stream["width"]),
        height=int(video_stream["height"]),
        fps=round(float(num) / float(demon)),
        video_codec=video_stream["codec_name"],
        video_bps=int(video_stream["bit_rate"]),
        audio_codec=audio_stream["codec_name"],
        audio_bps=int(audio_stream["bit_rate"]),
        file_size=file.stat().st_size,
    )


def generate_mediainfo_nfo(file, output_file):
    # Return if the nfo file exists.
    print(f"[NFO]: {output_file}")
    if output_file.exists():
        return
    # Get mediainfo text output.
    cmd = [MEDIA_INFO, str(file)]
    mediainfo = capture(cmd).decode("utf-8")
    # Remove the lines with Encoding settings, as they are not relevant.
    mediainfo = "\n".join(
        line
        for line in mediainfo.split("\n")
        if not line.startswith("Encoding settings")
    )
    # Wrie the nfo file next to the torrent file.
    with open(output_file, "w") as f:
        f.write(mediainfo)


def generate_thumbnails(video_file, meta, output_dir):
    print(f"[Thumbnails] ", end="")
    sys.stdout.flush()
    for i in range(1, 20):
        t = 120 * i
        print(".", end="")
        sys.stdout.flush()
        output = output_dir / f"capture_{i}.jpg"
        if output.exists() or meta.duration_sec < t:
            continue
        subprocess.run(
            [
                FFMPEG,
                "-y",
                "-v",
                "quiet",
                "-ss",
                str(t),
                "-i",
                str(video_file),
                "-vframes",
                "1",
                "-vf",
                f"scale=600:-1",
                output,
            ],
            check=True,
        )
    print()


def generate_description(meta, output_dir):
    if len(meta.actors) == 1:
        synopsis = f"La belle {meta.actors[0]} se fait sauter et prend son pied pour votre plus grand plaisir."
    else:
        synopsis = f"Les belles {', '.join(meta.actors[:-1])} et {meta.actors[-1]} se font sauter et prennent leur pied pour votre plus grand plaisir."

    title = f"[WowPorn] {', '.join(meta.actors)} - {meta.title} - 2016 WEBrip {meta.height}p {codec_simple_name(meta)}"
    print(title)

    title_file = output_dir / "title.txt"
    print(f"[Title]: {title_file}")

    description = f"""[center][size=200][color=#aa0000][b]{meta.title}[/b][/color][/size]

{title}

[img] [/img]
[img]https://www.genup.org/images/p18.jpg[/img]

[img]https://i.imgur.com/oiqE1Xi.png[/img]

[b]Origine :[/b] USA
[b]Durée :[/b] {round(meta.duration_sec / 60)} min {meta.duration_sec % 60} sec
[b]Acteurs :[/b] {', '.join(meta.actors)}
[b]Genre :[/b] XXX Hardcore

[img]https://i.imgur.com/HS8PPgH.png[/img]

{synopsis}

[img]https://i.imgur.com/fKYpxI3.png[/img]

[b]Qualité : WEBRip {meta.height}p[/b] 
[b]Format :[/b] MP4
[b]Codec Vidéo :[/b] {meta.video_codec} / {codec_simple_name(meta)}
[b]Débit Vidéo :[/b] {meta.video_bps / 1000:.0f} kb/s

[b]Langue(s) :[/b]
[img]https://flagcdn.com/20x15/us.png[/img] Anglais [2.0] | AAC à {meta.audio_bps / 1000:.0f} kb/s

[img]https://i.imgur.com/pkRSjYw.png[/img]

[b]Nombre de fichier(s) :[/b] 1
[b]Poids Total :[/b] {meta.file_size / 1000 / 1000 / 1000:.2f} Go
[/center]
    """
    # Write description file next to the torrent file
    description_file = output_dir / "description.txt"
    print(f"[Description]: {description_file}")
    with open(description_file, "wt", encoding="utf8") as f:
        f.write(description)


def codec_simple_name(meta):
    return {"hevc": "x265"}[meta.video_codec]


def generate_title(meta, output_dir):
    title = f"[WowPorn] {', '.join(meta.actors)} - {meta.title} - 2016 WEBrip {meta.height}p {codec_simple_name(meta)}"
    print(title)

    title_file = output_dir / "title.txt"
    print(f"[Title]: {title_file}")
    if not title_file.exists():
        # Write the title file next to the torrent file.
        with open(title_file, "w") as f:
            f.write(title)


def main():
    # Path of the input directory where videos are located.
    video_input_dir = pathlib.Path("Y:/Wow")
    # Local workdir relative to this script
    work_dir = pathlib.Path(__file__).parent.absolute() / "workdir"
    work_dir.mkdir(exist_ok=True)

    # Load `done.txt` in a set.
    text = subprocess.run([r"C:\Program Files\Transmission\transmission-remote.exe", "box1.local" , "-n", "transmission:transmission","-l"], capture_output=True, text=True)
    done = { os.path.splitext(line.split(" ")[-1])[0] for line in text.stdout.split("\n")}
    print(done)


    for file in pathlib.Path(work_dir).glob("*"):
        if file.name in done:
            print(f"Cleanup {file.name}")
            shutil.rmtree(file)
    

    # List files ending with crf\d+\.mp4
    for file in pathlib.Path(video_input_dir).glob("*_crf*.mp4"):
        if ".tmp." in file.name:
            print(f"Skip temp {file}")
            continue        
        if os.path.splitext(file.name)[0] in done:
            print(f"Skip completed {file}")
            continue
        print("-" * 80)
        print(file)
        print("-" * 80)

        print(f"[file] {file}")

        meta = get_video_metadata(file)

        # Create output directory in the workdir with the name of the video file.
        output_dir = work_dir / file.stem
        output_dir.mkdir(exist_ok=True)

   
        generate_thumbnails(file, meta, output_dir)
        generate_mediainfo_nfo(file, output_dir / f"{file.stem}.nfo")
        generate_description(meta, output_dir)

        print("-" * 80)
        # Locate a torrent file with the same name in working directory.
        torrent_file = output_dir / f"{file.stem}.torrent"
        if not torrent_file.exists():
            # Use transmission to create a torrent file.
            torrent_tmp_file = torrent_file.with_suffix(".tmp")
            cmd = [
                TRANSMISSION,
                "--private",
                "-t",
                "http://tracker.p2pconnect.net:8080/xxxxxxxxxxxxxxxxx/announce",
                "-o",
                str(torrent_tmp_file),
                str(file),
            ]
            print(f"[Run]: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            torrent_tmp_file.rename(torrent_file)


if __name__ == "__main__":
    main()
