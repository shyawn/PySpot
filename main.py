from dotenv import load_dotenv
import os
import re
import eyed3
import base64
from yt_dlp import YoutubeDL
from requests import post, get
import json
from urllib import request as rq
from urllib.parse import quote

from flask import Flask, session, request, redirect, url_for

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(64)

client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")

redirect_uri = 'http://localhost:5000/callback'
scope = 'playlist-read-private'

download_path = "./downloads"

cache_handler = FlaskSessionCacheHandler(session)
sp_oauth = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope=scope,
    cache_handler=cache_handler,
    show_dialog=True
)

sp = Spotify(auth_manager=sp_oauth)

@app.route("/")
def home():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    return redirect(url_for('get_playlists'))

@app.route("/callback")
def callback():
    sp_oauth.get_access_token(request.args['code'])
    return redirect(url_for('get_playlists'))

pl_uri = os.getenv("PL_URI")

@app.route("/get_playlists")
def get_playlists():
    if not sp_oauth.validate_token(cache_handler.get_cached_token()):
        auth_url = sp_oauth.get_authorize_url()
        return redirect(auth_url)
    
    # playlist = sp.current_user_playlists()
    # # print(playlist)
    # playlist_info = [(pl['name'], pl['uri']) for pl in playlist['items']]
    # playlist_html = '<br>'.join([f"{name}: {url}" for name, url in playlist_info])
    
    # return playlist_html

    p_details = get_playlist_details(pl_uri)
    p_show = '<br>'.join([f"{item['track_name']}: {item['artist_name']}" for item in p_details])
    return p_show

def normalize_str(string):
    return string.translate(str.maketrans('\\/:*?"<>|', "__       "))

def get_playlist_details(playlist_uri):
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

def download_tracks(playlist_uri):
    playlist_details = get_playlist_details(playlist_uri)
    path = download_dir(playlist_details["playlist_name"])
    tracks = check_existing_tracks(playlist_details, path)
    print(
        f"\033[1m\033[33m[info] Downloading {len(tracks)} tracks from {playlist_details['playlist_name']}...\033[0m"
    )
    with YoutubeDL(get_ydl_opts(path)) as ydl:
        for track in tracks:
            html = rq.urlopen(
                f"https://www.youtube.com/results?search_query={track['uri']}"
            )
            video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())

            if video_ids:
                url = "https://www.youtube.com/watch?v=" + video_ids[0]
                metadata = ydl.extract_info(url, download=False)
                downloaded_track = ydl.download([url])

                add_track_metadata(metadata["id"], track, path)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

# def get_token():
#     auth_string = client_id + ":" + client_secret
#     auth_bytes = auth_string.encode("utf-8")
#     auth_base64 = str(base64.b64encode(auth_bytes), "utf-8")

#     url = "https://accounts.spotify.com/api/token"
#     headers = {
#         "Authorization": "Basic " + auth_base64,
#         "Content-Type": "application/x-www-form-urlencoded" 
#     }
#     data = {"grant_type": "client_credentials"}
#     result = post(url, headers=headers, data=data)
#     json_result = json.loads(result.content)
#     token = json_result["access_token"]
#     return token

# def get_auth_headers(token):
#     return {"Authorization": "Bearer " + token}

# def search_for_artist(token, artist_name):
#     url = "https://api.spotify.com/v1/search"
#     headers = get_auth_headers(token)
#     query = f"?q={artist_name}&type=artist&limit=1"

#     query_url = url + query
#     result = get(query_url, headers=headers)
#     json_result = json.loads(result.content)["artists"]["items"]
#     if len(json_result) == 0:
#         print("No artist with this name exists...")
#         return None
#     return json_result[0]

# def get_songs_by_artist(token, artist_id):
#     url = f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks?country=US"
#     headers = get_auth_headers(token)
#     result = get(url, headers=headers)
#     json_result = json.loads(result.content)["tracks"]
#     return json_result
    
# token = get_token()
# result = search_for_artist(token, "ACDC")
# artist_id = result["id"]
# songs = get_songs_by_artist(token, artist_id)

# for idx, song in enumerate(songs):
#     print(f"{idx + 1}. {song['name']}")

if __name__ == '__main__':
    app.run(debug=True)