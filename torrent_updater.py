import json
import logging
from tmdbv3api import TMDb, Search, TV
from tpblite import TPB
from transmission_rpc import Client
import os

TV_SHOWS_FOLDER = "/Users/Ishay/Downloads/tests"
CACHED_EPISODE = "cached.json"
LOG_FILE = "torrent_updater.log"
HOST = "192.168.1.204"
USERNAME = os.environ["TRANSMISSION_USERNAME"]
PASSWORD = os.environ["TRANSMISSION_PASSWORD"]
TMDB_API_KEY = os.environ["TMDB_API_KEY"]

tmdb = TMDb()
tmdb.api_key = TMDB_API_KEY
search = Search(tmdb)
tv = TV(tmdb)
tpb = TPB()
transmission = Client(host=HOST, port=9091, username=USERNAME, password=PASSWORD)

logger = logging.getLogger("torrent_updater")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOG_FILE)
fh.setLevel(logging.DEBUG)
logger.addHandler(fh)


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
    episode = {
        "season_number": next_episode.season_number,
        "episode_number": next_episode.episode_number,
        "show": show,
    }
    with open(f"{TV_SHOWS_FOLDER}/{show}/{CACHED_EPISODE}", "w") as openfile:
        json.dump(episode, openfile)
    return episode


def find_torrent(episode):
    search_term = f"{episode['show']} S{str(episode['season_number']).zfill(2)}E{str(episode['episode_number']).zfill(2)}"
    torrents = tpb.search(search_term + " hdr 2160p")
    if len(torrents) > 0:
        logger.log(msg=f"found {search_term} hdr 2160p", level=1)
        return torrents[0]
    torrents = tpb.search(search_term + " 2160p")
    if len(torrents) > 0:
        logger.log(msg=f"found {search_term} 2160p", level=1)
        return torrents[0]
    torrents = tpb.search(search_term + " 1080p")
    if len(torrents) > 0:
        logger.log(msg=f"found {search_term} 1080p", level=1)
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
        if download_torrent(episode):
            update_cached_episode(show)
