# from dotenv import load_dotenv
import os
from utils import download_tracks

from flask import Flask, session, request, redirect, url_for

from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import FlaskSessionCacheHandler

# load_dotenv()

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
    
    playlist = sp.current_user_playlists()
    # print(playlist)
    playlist_info = [(pl['name'], pl['uri']) for pl in playlist['items']]
    playlist_html = '<br>'.join([f"{name}: {url}" for name, url in playlist_info])
    

    # p_details = get_playlist_details(pl_uri)
    # p_show = '<br>'.join([f"{item['track_name']}: {item['artist_name']}" for item in p_details])
    download_tracks(sp, pl_uri)
    # return p_show
    return playlist_html

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)