import os
import urllib.parse
from datetime import date, timedelta, datetime
from typing import Optional
import requests

import xmltodict
from jellyfin_api_client import AuthenticatedClient
from jellyfin_api_client.api.items import get_items
from jellyfin_api_client.api.tv_shows import get_episodes
from jellyfin_api_client.models import ItemFields, BaseItemKind, BaseItemDto
from tpblite import TPB
from transmission_rpc import Client

TV_SHOWS_FOLDER = "/mnt/media/Shows"
TRANSMISSION_HOST = "192.168.1.204"
TRANSMISSION_USERNAME = os.environ["TRANSMISSION_USERNAME"]
TRANSMISSION_PASSWORD = os.environ["TRANSMISSION_PASSWORD"]
JELLYFIN_SERVER = "http://192.168.1.206:8096"
JELLYFIN_API_KEY = os.environ["JELLYFIN_API_KEY"]
BT4G_SERVER = "https://bt4gprx.com/search"

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


def get_episodes_from_jellyfin() -> list[BaseItemDto]:
    """
    Queries Jellyfin API for missing episodes.
    :return: List of missing episodes.
    """
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


def find_torrent(episode: BaseItemDto) -> Optional[str]:
    """
    Calls :func:`get_valid_torrent` with some suffixes with video quality.
    :param episode: Episode object returned from jellyfin.
    :return: Magnet link.
    """
    torrent = get_valid_torrent(episode, "hdr 2160p")
    if torrent:
        return torrent
    torrent = get_valid_torrent(episode, "2160p")
    if torrent:
        return torrent
    torrent = get_valid_torrent(episode, "1080p")
    if torrent:
        return torrent


def get_valid_torrent(episode: BaseItemDto, suffix: str) -> Optional[str]:
    """
    Searches tpb and bt4g for valid torrents (actual videos) and returns a magnet link if found.
    :param episode: Episode object returned from jellyfin.
    :param suffix: What to append after the search term, e.g. "2160p hdr".
    :return: Magnet link.
    """
    parsed_show_name = episode.series_name.replace("'", "")
    search_term = f"{parsed_show_name} S{str(episode.parent_index_number).zfill(2)}E{str(episode.index_number).zfill(2)} {suffix}"

    tpb_torrents = [
        torrent.magnetlink
        for torrent in tpb.search(search_term)
        if ":" in torrent.upload_date.split(" ")[1]
        and torrent.upload_date.split(" ")[0] >= episode.premiere_date.strftime("%m-%d")
        and (torrent.is_trusted or torrent.is_vip)
    ]
    if len(tpb_torrents) > 0:
        return tpb_torrents[0]

    bt4g_result = requests.get(
        f"{BT4G_SERVER}?{urllib.parse.urlencode({'q': search_term, 'page': 'rss'})}",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        },
    )
    bt4g_raw_res = xmltodict.parse(bt4g_result.text)["rss"]["channel"]
    if "item" in bt4g_raw_res:
        bt4g_torrents = [
            item["link"]
            for item in xmltodict.parse(bt4g_result.text)["rss"]["channel"]["item"]
            if "<br>Movie<br>" in item["description"]
            and datetime.strptime(item["pubDate"], "%a,%d %b %Y %H:%M:%S %z").date()
            >= episode.premiere_date.date()
        ]
        if len(bt4g_torrents) > 0:
            return bt4g_torrents[0]


def download_torrent(episode: BaseItemDto) -> None:
    """
    Calls :func:`find_torrent`, and if magnet link is found, pushes it to Transmission.
    :param episode: Episode object returned from jellyfin.
    """
    torrent = find_torrent(episode)
    if torrent:
        transmission.add_torrent(
            torrent,
            download_dir=f"{TV_SHOWS_FOLDER}/{episode.series_name}/Season {episode.parent_index_number}",
        )


if __name__ == "__main__":
    for ep in get_episodes_from_jellyfin():
        download_torrent(ep)
