import json
import logging
import re
import os

from tmdbv3api import TMDb, Search, TV
from tpblite import TPB
from transmission_rpc import Client

TV_SHOWS_FOLDER = "/mnt/media/Shows"
CACHED_EPISODE = "cached.json"
LOG_FILE = "torrent_updater.log"
HOST = "192.168.1.204"
USERNAME = os.environ["TRANSMISSION_USERNAME"]
PASSWORD = os.environ["TRANSMISSION_PASSWORD"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG)
tmdb = TMDb()
tmdb.api_key = TMDB_API_KEY
search = Search(tmdb)
tv = TV(tmdb)
tpb = TPB()
transmission = Client(host=HOST, port=9091, username=USERNAME, password=PASSWORD)


def get_shows_from_folder():
    return [f.name for f in os.scandir(TV_SHOWS_FOLDER) if f.is_dir()]


def get_cached_episode(show):
    if CACHED_EPISODE in [f.name for f in os.scandir(f"{TV_SHOWS_FOLDER}/{show}")]:
        with open(f"{TV_SHOWS_FOLDER}/{show}/{CACHED_EPISODE}", "r") as openfile:
            episode = json.load(openfile)
    else:
        episode = update_cached_episode(show)
    return episode


def update_cached_episode(show):
    show_id = search.tv_shows(show)[0].id
    next_episode = tv.details(show_id).next_episode_to_air
    if next_episode is None:
        return
    episode = {
        "season_number": next_episode["season_number"],
        "episode_number": next_episode["episode_number"],
        "air_date": next_episode["air_date"],
        "show": show,
    }
    with open(f"{TV_SHOWS_FOLDER}/{show}/{CACHED_EPISODE}", "w") as openfile:
        json.dump(episode, openfile)
    return episode


def find_torrent(episode):
    search_term = f"{episode['show']} S{str(episode['season_number']).zfill(2)}E{str(episode['episode_number']).zfill(2)}"
    regex = re.compile("^" + episode["show"].replace(" ", "[. ]"), re.IGNORECASE)

    torrents = [
        torrent
        for torrent in tpb.search(search_term + " hdr 2160p")
        if regex.search(torrent.title)
    ]
    if len(torrents) > 0:
        logging.log(msg=f"Found {search_term} hdr 2160p", level=7)
        return torrents[0]

    torrents = [
        torrent
        for torrent in tpb.search(search_term + " 2160p")
        if regex.search(torrent.title)
    ]
    if len(torrents) > 0:
        logging.log(msg=f"Found {search_term} 2160p", level=7)
        return torrents[0]

    torrents = [
        torrent
        for torrent in tpb.search(search_term + " 1080p")
        if regex.search(torrent.title)
    ]
    if len(torrents) > 0:
        logging.log(msg=f"Found {search_term} 1080p", level=7)
        return torrents[0]


def download_torrent(episode):
    torrent = find_torrent(episode)
    if torrent:
        transmission.add_torrent(
            torrent.magnetlink,
            download_dir=f"{TV_SHOWS_FOLDER}/{episode['show']}/Season {episode['season_number']}",
        )
        return True
    else:
        return False


if __name__ == "__main__":
    show_names = get_shows_from_folder()

    for show in show_names:
        episode = get_cached_episode(show)
        if episode is not None and download_torrent(episode):
            update_cached_episode(show)
