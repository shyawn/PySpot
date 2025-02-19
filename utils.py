from dotenv import load_dotenv
import os
import re
import eyed3
from yt_dlp import YoutubeDL
from urllib import request as rq
from urllib.parse import quote

load_dotenv()

download_path = "./downloads"

def normalize_str(string):
    return string.translate(str.maketrans('\\/:*?"<>|', "__       "))

def get_playlist_details(sp, playlist_uri):
    offset = 0
    fields = "items.track.track_number,items.track.name,items.track.artists.name,items.track.album.name,items.track.album.release_date,total,items.track.album.images"
    playlist_name = sp.playlist(playlist_uri)["name"]
    playlist_items = sp.playlist_items(
        playlist_uri,
        offset=offset,
        fields=fields,
        additional_types=["track"],
    )["items"]

    playlist_tracks = []
    while len(playlist_items) > 0:
        for item in playlist_items:
            if item["track"]:
                track_name = normalize_str(item["track"]["name"])
                artist_name = normalize_str(
                    item["track"]["artists"][0]["name"]
                )
                playlist_tracks.append(
                    {
                        "uri": quote(
                            f'{track_name.replace(" ", "+")}+{artist_name.replace(" ", "+")}'
                        ),
                        "file_name": f"{artist_name} - {track_name}",
                        "track_name": track_name,
                        "artist_name": artist_name,
                        "album_name": normalize_str(
                            item["track"]["album"]["name"]
                        ),
                        "album_date": item["track"]["album"]["release_date"],
                        "track_number": item["track"]["track_number"],
                        "album_art": item["track"]["album"]["images"][0]["url"],
                    }
                )

        # Reduce playlist items by increasing offset
        offset = offset + len(playlist_items)
        playlist_items = sp.playlist_items(
            playlist_uri,
            offset=offset,
            fields=fields,
            additional_types=["track"],
        )["items"]

    return {"playlist_name": playlist_name, "playlist_tracks": playlist_tracks}

def download_dir(dir_name):
    path = f"{download_path}/{dir_name}"

    if os.path.exists(path):
        return path
    
    try:
        os.makedirs(path)
        return path
    except OSError:
            print("Creation of the download directory failed")

def check_existing_tracks(playlist, path):
    existing_tracks = os.listdir(path)
    tracks = [
        track
        for track in playlist["playlist_tracks"]
        if f"{track['file_name']}.mp3" not in existing_tracks
    ]
    return tracks

def get_ydl_opts(path):
    return {
        "format": "bestaudio/best",
        "outtmpl": f"{path}/%(id)s.%(ext)s",
        "ignoreerrors": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
    }

def add_track_metadata(track_id, metadata, path):
    audiofile = eyed3.load(f"{path}/{track_id}.mp3")
    if audiofile.tag == None:
        audiofile.initTag()

    # Add basic tags
    audiofile.tag.title = metadata["track_name"]
    audiofile.tag.album = metadata["album_name"]
    audiofile.tag.artist = metadata["artist_name"]
    audiofile.tag.release_date = metadata["album_date"]
    audiofile.tag.track_num = metadata["track_number"]

    album_art = rq.urlopen(metadata["album_art"]).read()
    audiofile.tag.images.set(3, album_art, "image/jpeg")
    audiofile.tag.save()

    # Update downloaded file name
    src = f"{path}/{track_id}.mp3"
    dist = f"{path}/{metadata['file_name']}.mp3"
    os.rename(src, dist)

def download_tracks(sp, playlist_uri):
    playlist_details = get_playlist_details(sp, playlist_uri)
    path = download_dir(playlist_details["playlist_name"])
    tracks = check_existing_tracks(playlist_details, path)
    print(
        f"\033[1m\033[33m[info] Downloading {len(tracks)} tracks from {playlist_details['playlist_name']}...\033[0m"
    )
    with YoutubeDL(get_ydl_opts(path)) as ydl:
        for track in tracks:
            # print("SEARCH URL: ", f"https://www.youtube.com/results?search_query={track['uri']}")
            html = rq.urlopen(
                f"https://www.youtube.com/results?search_query={track['uri']}"
            )
            video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())

            if video_ids:
                url = "https://www.youtube.com/watch?v=" + video_ids[0]
                # metadata = ydl.extract_info(url, download=False)
                
                try:
                    metadata = ydl.extract_info(url, download=False)
                    if not metadata:
                        raise ValueError("Metadata extraction failed")
                except Exception as e:
                    print(f"Error extracting metadata: {e}")
                    continue
                downloaded_track = ydl.download([url])

                add_track_metadata(metadata["id"], track, path)