import os
from datetime import date, timedelta

from jellyfin_api_client import AuthenticatedClient
from jellyfin_api_client.api.items import get_items
from jellyfin_api_client.api.tv_shows import get_episodes
from jellyfin_api_client.models import ItemFields, BaseItemKind
from tpblite import TPB
from transmission_rpc import Client

TV_SHOWS_FOLDER = "/mnt/media/Shows"
TRANSMISSION_HOST = "192.168.1.204"
TRANSMISSION_USERNAME = os.environ["TRANSMISSION_USERNAME"]
TRANSMISSION_PASSWORD = os.environ["TRANSMISSION_PASSWORD"]
JELLYFIN_SERVER = "http://192.168.1.206:8096"
JELLYFIN_API_KEY = os.environ["JELLYFIN_API_KEY"]

tpb = TPB()
transmission = Client(
    host=TRANSMISSION_HOST,
    port=9091,
    username=TRANSMISSION_USERNAME,
    password=TRANSMISSION_PASSWORD,
)
jellyfin = AuthenticatedClient(
    base_url=JELLYFIN_SERVER,
    token=f'Token="{JELLYFIN_API_KEY}"',
    prefix="MediaBrowser",
)


def get_episodes_from_jellyfin():
    missing_episodes = []
    shows = get_items.sync(
        client=jellyfin,
        include_item_types=[BaseItemKind.SERIES],
        fields=[ItemFields.PROVIDERIDS],
        recursive=True,
    ).items
    for show in shows:
        episodes = get_episodes.sync(client=jellyfin, series_id=show.id).items
        for episode in episodes:
            if (
                episode.premiere_date
                and episode.location_type == "Virtual"  # episode is missing
                and (
                    (date.today() - timedelta(days=7))
                    <= episode.premiere_date.date()
                    <= (date.today() - timedelta(days=1))
                )  # aired sometime in the past week
                and episode.parent_index_number > 0  # not a special
            ):
                missing_episodes.append(episode)

    return missing_episodes


def find_torrent(episode):
    torrent = get_valid_torrent(episode, "hdr 2160p")
    if torrent:
        return torrent
    torrent = get_valid_torrent(episode, "2160p")
    if torrent:
        return torrent
    torrent = get_valid_torrent(episode, "1080p")
    if torrent:
        return torrent


def get_valid_torrent(episode, suffix):
    parsed_show_name = episode.series_name.replace("'", "")
    search_term = f"{parsed_show_name} S{str(episode.parent_index_number).zfill(2)}E{str(episode.index_number).zfill(2)}"
    torrents = [
        torrent
        for torrent in tpb.search(f"{search_term} {suffix}")
        if ":" in torrent.upload_date.split(" ")[1]
        and torrent.upload_date.split(" ")[0] >= episode.premiere_date.strftime("%m-%d")
        and (torrent.is_trusted or torrent.is_vip)
    ]
    if len(torrents) > 0:
        return torrents[0]


def download_torrent(episode):
    torrent = find_torrent(episode)
    if torrent:
        transmission.add_torrent(
            torrent.magnetlink,
            download_dir=f"{TV_SHOWS_FOLDER}/{episode.series_name}/Season {episode.parent_index_number}",
        )


if __name__ == "__main__":
    for ep in get_episodes_from_jellyfin():
        download_torrent(ep)
