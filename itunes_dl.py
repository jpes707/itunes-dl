# pylint: disable=W1401

import os
import subprocess
import sys
import eyed3
import json
import requests
import shutil
import re
import atexit
import lyricsgenius
import warnings
from fuzzywuzzy import fuzz, process
from titlecase import titlecase
from time import time, sleep
from threading import Thread
from webptools import dwebp

use_legacy_names = True
download_lyrics = True  # Genius API key must be in `genius-key.txt` if True


def get_relative_path(*args):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *args)


legacy_names = {'The Chicks': 'Dixie Chicks', 'Lady A': 'Lady Antebellum'}
if download_lyrics:
    genius = lyricsgenius.Genius(open(get_relative_path('genius-key.txt'), 'r').read(), skip_non_songs=True, remove_section_headers=True)
    genius.verbose = False  # suppress print messages
warnings.filterwarnings('ignore', category=DeprecationWarning)

pending_thread_song = None


def get_titlecase(s, override_legacy_rename=False):
    if not s:
        return ''
    s = s.replace('&amp;', 'and')
    feat_idx = s.find('\x28feat.')
    if feat_idx != -1:
        feat_end_idx = s.index('\x29', feat_idx)
        feat_str = s[feat_idx:feat_idx+7] + get_titlecase(s[feat_idx+7:feat_end_idx]) + '\x29' + get_titlecase(s[feat_end_idx+1:])
        s = s[:feat_idx]
    else:
        feat_str = ''
    if s.isupper() or s.islower():
        ret_str = s
    else:
        ret_str = titlecase(s)
    ret_str += feat_str
    if use_legacy_names and not override_legacy_rename:
        for key in legacy_names:
            ret_str = ret_str.replace(key, legacy_names[key])
    return ret_str


def get_lyrics(track, artist):
    try:
        lyrics = genius.search_song(track, artist).lyrics
        lyrics_stripped = ''  # bracket tags removed like "[Pre-Chorus]"
        for line in lyrics.splitlines():
            if not line or (line[0] != '[' and line[-1] != ']'):
                lyrics_stripped += line.replace('  ', ' ') + '\n'
        lyrics_stripped = lyrics_stripped[:-1]
        lyrics_stripped = re.sub(r'[0-9]+EmbedShare URLCopyEmbedCopy','',lyrics)
        return lyrics_stripped
    except:
        return None


def get_youtube_music_song_metadata(song_obj):
    song_name = song_obj['flexColumns'][0]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][0]['text']
    artist_name = song_obj['flexColumns'][1]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][2]['text']
    album_name =  song_obj['flexColumns'][1]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][4]['text'] if len(song_obj['flexColumns']) > 2 else None
    song_url = 'https://music.youtube.com/watch?v={}'.format(song_obj['flexColumns'][0]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][0]['navigationEndpoint']['watchEndpoint']['videoId'])
    return {'youtube_song_name': song_name, 'youtube_album_name': album_name, 'youtube_artist_name': artist_name, 'song_url': song_url}


def get_song_url(track, artist, do_manual, track_num=None, album='', deluxe_album=''):
    try:
        song_search_url = 'https://music.youtube.com/search?q={}'.format((track + '+' + artist + '+' + album).replace(' ', '+'))
        print('Searching... {}'.format(song_search_url))
        res = requests.get(song_search_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'})
        song_search_res_json = res.text
        res.close()
        song_search_res_json = song_search_res_json[song_search_res_json.rindex('data:')+7:]
        song_search_res_json = song_search_res_json[:song_search_res_json.index('\'')]
        song_search_res_json = bytes(song_search_res_json, 'utf-8').decode('unicode_escape')
        song_search_res_json = song_search_res_json.replace(r'\"', '\x1a')  # replace \\" with substitute
        song_search_res_json = song_search_res_json.replace('\\', '')  # remove all \
        song_search_res_json = song_search_res_json.replace('\x1a', r'\"')  # replace substitute with \"
        song_search_res = json.loads(song_search_res_json)
        potential_songs = []
        # refer to sample-youtube-music-json.txt for an example of the song_search_res object
        top_result_idx = 0 if 'tabRenderer' in song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0] else 1
        print(song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][top_result_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['flexColumns'][0]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][0]['navigationEndpoint']['watchEndpoint']['watchEndpointMusicSupportedConfigs']['watchEndpointMusicConfig']['musicVideoType'])
        if 'navigationEndpoint' in song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][top_result_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['flexColumns'][0]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][0] and song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][top_result_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['flexColumns'][0]['musicResponsiveListItemFlexColumnRenderer']['text']['runs'][0]['navigationEndpoint']['watchEndpoint']['watchEndpointMusicSupportedConfigs']['watchEndpointMusicConfig']['musicVideoType'] == 'MUSIC_VIDEO_TYPE_ATV':
            print('{} top result is a SONG'.format(track))
            song_obj = song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][top_result_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']
            print(song_obj)
            potential_songs.append(get_youtube_music_song_metadata(song_obj))
        for i in range(1, len(song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'])):
            if song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][i]['musicShelfRenderer']['title']['runs'][0]['text'] == 'Songs':
                songs_idx = i
                break
        else:
            return None
        for i in range(3):
            song_obj = song_search_res['contents']['tabbedSearchResultsRenderer']['tabs'][0]['tabRenderer']['content']['sectionListRenderer']['contents'][songs_idx]['musicShelfRenderer']['contents'][i]['musicResponsiveListItemRenderer']
            potential_songs.append(get_youtube_music_song_metadata(song_obj))
        for idx, song in enumerate(potential_songs):
            potential_songs[idx]['song_name_score'] = fuzz.ratio(track, song['youtube_song_name'])
            potential_songs[idx]['album_name_score'] = max(fuzz.ratio(album, song['youtube_album_name']), fuzz.ratio(deluxe_album, song['youtube_album_name'])) if song['youtube_album_name'] else 100
            potential_songs[idx]['artist_name_score'] = fuzz.ratio(artist, song['youtube_artist_name'])
            potential_songs[idx]['overall_score'] = potential_songs[idx]['song_name_score'] * 2 + potential_songs[idx]['album_name_score'] + potential_songs[idx]['artist_name_score'] * 2  # 500 is a perfect match, 0 is no match
        chosen_song = sorted(potential_songs, key=lambda i: i['overall_score'], reverse=True)[0]
        # print(chosen_song['song_name_score'], chosen_song['album_name_score'], chosen_song['artist_name_score'])
        if do_manual or chosen_song['song_name_score'] < (50 if 'remix' not in track.lower() else 90) or chosen_song['album_name_score'] < 50 or chosen_song['artist_name_score'] < 50:
            global pending_thread_song, url_pending
            if track_num:
                url_pending[track_num - 1] = True
            while pending_thread_song != track:
                sleep(1)
            print('WARNING! AN INCORRECT SONG MAY BE DOWNLOADED. Track "{}" has a low song, album, and/or artist match score => {}'.format(track, chosen_song))
            manual_url_ask = input('Would you like to manually provide a correct URL (y/[n])? ')
            if manual_url_ask.lower() == 'y':
                chosen_song['song_url'] = input('Paste a URL to any MP3/video on the internet for track "{}" (can be on YouTube, does not have to be): ')
            if manual_url_ask.lower().startswith('http'):
                chosen_song['song_url'] = manual_url_ask
        if track_num:
            url_pending[track_num - 1] = False
        return chosen_song['song_url']
    except:
        # print(song_search_res_json)
        return None


def attempt_youtube_dl_download(downloads_path, track_file, song_url):
    try:
        subprocess.check_output('youtube-dl -x --audio-format mp3 --audio-quality 0 -o "{}.%(ext)s" "{}"'.format(os.path.join(downloads_path, track_file), song_url))
        return True
    except:
        return False


def download_song(track, track_num, is_deluxe, album_artist, album_artist_current, album_name, deluxe_album_name, album_genre, album_year, album_artwork_path, downloads_path, do_manual):
    for _ in range(1):
        song_url = get_song_url(track, album_artist, do_manual, track_num, album_name, deluxe_album_name)
        if song_url:
            break
    else:
        print('WARNING! Song will not be downloaded because URL could not be found after ten tries: "{}" => {}'.format(track, 'https://music.youtube.com/search?q={}'.format((track + '+' + album_artist + '+' + album_name).replace(' ', '+'))))
        url_pending[track_num - 1] = False
        return
    
    track_file = '{} {}'.format(str(track_num).zfill(2), track.replace(':', '').replace('?', '').replace('!', '').replace('"', '').replace('*', '').replace('/', '').replace('\\', ''))
    track_path = os.path.join(downloads_path, '{}.mp3'.format(track_file))
    
    print('{} => {}'.format(track, song_url))
    
    for _ in range(60):
        song_downloaded = attempt_youtube_dl_download(downloads_path, track_file, song_url)
        if song_downloaded:
            break
        else:
            sleep(5)
    else:
        print('WARNING! Song will not be downloaded because youtube-dl failed sixty times: "{}" at {}'.format(track, song_url))
        return
    
    audiofile = eyed3.load(track_path)
    if (audiofile.tag == None):
        audiofile.initTag()  # audiofile.initTag(version=(2, 3, 0))
    audiofile.tag.title = track
    audiofile.tag.artist = album_artist
    audiofile.tag.album = album_name
    audiofile.tag.album_artist = album_artist
    audiofile.tag.genre = album_genre
    audiofile.tag.original_release_date = album_year
    audiofile.tag.recording_date = album_year
    audiofile.tag.release_date = album_year
    audiofile.tag.track_num = track_num

    audiofile.tag.images.set(3, open(album_artwork_path, 'rb').read(), 'image/png')
    audiofile.tag.disc_num = 2 if is_deluxe else 1

    if download_lyrics:
        for _ in range(10):
            lyrics = get_lyrics(track, album_artist)
            if lyrics:
                audiofile.tag.lyrics.set(lyrics)
                break
        else:
            print('WARNING! Lyrics will not be downloaded because Genius did not return lyrics ten times: "{}"'.format(track))
    audiofile.tag.save(encoding='utf-8', version=eyed3.id3.ID3_V2_4)


def main(album_url=None, normal_url=None, song_index=None):
    if not album_url:
        album_url = input('Apple Music URL (https://music.apple.com/xxx) for the album: ')
    if normal_url and normal_url.lower() == 'n':
        normal_url = album_url
    do_manual = normal_url and normal_url.lower() == 'x'
    if not normal_url or do_manual:
        normal_url = album_url
        album_deluxe_ask = input('Is this album a deluxe version (y/[n])? ')
        if album_deluxe_ask.lower() == 'y':
            normal_url = input('Apple Music URL (https://music.apple.com/xxx) for the NON-DELUXE album version: ')
        if album_deluxe_ask.lower().startswith('http'):
            normal_url = album_deluxe_ask
    
    if not os.path.exists(get_relative_path('cache', 'artwork')):
        if not os.path.exists(get_relative_path('cache')):
            os.mkdir(get_relative_path('cache'))
        os.mkdir(get_relative_path('cache', 'artwork'))
    if not os.path.exists(get_relative_path('cache', 'itunes_path.txt')):
        itunes_path = input('What is the path of your system\'s iTunes folder (e.g. D:\Music\iTunes)? ')
        f = open(get_relative_path('cache', 'itunes_path.txt'), 'w+')
        f.write(itunes_path)
        f.close()
    else:
        f = open(get_relative_path('cache', 'itunes_path.txt'), 'r')
        itunes_path = f.read()
        f.close()
    itunes_add_path = os.path.join(itunes_path, 'iTunes Media', 'Automatically Add to iTunes')

    exists_count = 0
    while os.path.exists(get_relative_path('cache', 'TEMP-{}'.format(exists_count))):
        exists_count += 1
    downloads_path = get_relative_path('cache', 'TEMP-{}'.format(exists_count))
    os.mkdir(downloads_path)
    atexit.register(shutil.rmtree, downloads_path)

    album_res = requests.get(normal_url).text
    schema_start_string = '<script name="schema:music-album" type="application/ld+json">'
    schema_start_index = album_res.index(schema_start_string)
    album_schema = json.loads(album_res[schema_start_index + len(schema_start_string) : album_res.index('</script>', schema_start_index)])

    album_name = get_titlecase(album_schema['name'])
    normal_album_track_count = len(album_schema['tracks'])
    album_year = int(album_schema['datePublished'][:4])
    album_artist = get_titlecase(album_schema['byArtist']['name'])
    album_artist_current = get_titlecase(album_schema['byArtist']['name'], True)
    album_genre = album_schema['genre'][0].replace('&amp;', '&')
    
    webp_artwork_path = get_relative_path('cache', 'artwork', '{}-{}-{}.webp'.format(album_artist.replace(' ', '_'), album_name.replace(' ', '_'), album_year).replace('?', '').replace('"', '').replace('*', '').replace('/', '').replace('\\', ''))
    album_artwork_path = get_relative_path('cache', 'artwork', '{}-{}-{}.png'.format(album_artist.replace(' ', '_'), album_name.replace(' ', '_'), album_year).replace('?', '').replace('"', '').replace('*', '').replace('/', '').replace('\\', ''))
    if not os.path.exists(album_artwork_path):
        artwork_search_str = album_res[:album_res.index(' 1000w')]
        artwork_search_str = artwork_search_str[artwork_search_str.rindex('https://'):]
        album_artwork_url = artwork_search_str.strip()
        print(album_artwork_url)
        r = requests.get(album_artwork_url, stream=True)
        print(webp_artwork_path)
        if r.status_code == 200:
            with open(webp_artwork_path, 'wb+') as f:
                 r.raw.decode_content = True
                 shutil.copyfileobj(r.raw, f)
            dwebp(webp_artwork_path, album_artwork_path, '-o')
            os.remove(webp_artwork_path)
    
    if normal_url != album_url:
        deluxe_album_res = requests.get(album_url).text
        schema_start_index = deluxe_album_res.index(schema_start_string)
        album_schema = json.loads(deluxe_album_res[schema_start_index + len(schema_start_string) : deluxe_album_res.index('</script>', schema_start_index)])

    deluxe_album_track_count = len(album_schema['tracks'])
    deluxe_album_name = get_titlecase(album_schema['name'])
    album_tracks = [get_titlecase(track['name']) for track in album_schema['tracks']]
    is_deluxe_list = [False] * normal_album_track_count + [True] * (deluxe_album_track_count - normal_album_track_count)

    if song_index:
        song_index = int(song_index)
        deluxe_album_track_count = 1
        album_tracks = [album_tracks[song_index - 1]]
        is_deluxe_list = [is_deluxe_list[song_index - 1]]
    
    print(album_name, album_artist, album_genre, deluxe_album_track_count, album_year, album_tracks)
    print()

    thread_list = []
    global url_pending
    url_pending = [None] * len(album_tracks)
    for idx, track in enumerate(album_tracks):
        # print('Downloading "{}" (track {}/{})...'.format(track, idx+1, album_track_count))
        current_thread = Thread(target=download_song, args=(track, idx+1, is_deluxe_list[idx], album_artist, album_artist_current, album_name, deluxe_album_name, album_genre, album_year, album_artwork_path, downloads_path, do_manual))
        current_thread.start()
        # download_song(track, idx+1, album_artist, album_artist_current, album_name, album_genre, album_year, album_artwork_path, downloads_path)
        thread_list.append(current_thread)
    while None in url_pending:
        sleep(1)
    for idx, thread in enumerate(thread_list):
        if not url_pending[idx]:
            thread.join()
    for idx, thread in enumerate(thread_list):
        if url_pending[idx]:
            global pending_thread_song
            pending_thread_song = album_tracks[idx]
            thread.join()

    print()

    track_filenames = ['{} {}.mp3'.format(str(idx+1).zfill(2), track.replace(':', '').replace('?', '').replace('!', '').replace('"', '').replace('*', '').replace('/', '').replace('\\', '')) for idx, track in enumerate(album_tracks)]
    for track_filename in track_filenames:
        try:
            os.replace(os.path.join(downloads_path, track_filename), os.path.join(itunes_add_path, track_filename))
            print('{} is complete!'.format(track_filename))
        except:
            print('{} was NOT downloaded.'.format(track_filename))
    # sleep(5)
    # album_folder_path = os.path.join(itunes_path, 'iTunes Media', 'Music', album_artist, album_name)
    # for track_filename in track_filenames:
    #     track_path = os.path.join(album_folder_path, '1-' + track_filename)
    #     audiofile = eyed3.load(track_path)
    #     audiofile.tag.save(encoding='utf-8', version=eyed3.id3.ID3_V2_3)


if __name__ == '__main__':
    if len(sys.argv) > 3:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 2:
        main(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
