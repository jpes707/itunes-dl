# pylint: disable=W1401

import os
import sys
import eyed3
import json
import requests
import shutil
import re
import atexit
import json
import lyricsgenius
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
    genius = lyricsgenius.Genius(open(get_relative_path('genius-key.txt'), 'r').read())


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
        return lyrics_stripped
    except:
        return None


def get_song_url(track, artist, album=''):
    try:
        song_search_url = 'https://music.youtube.com/search?q={}'.format((track + '+' + artist + '+' + album).replace(' ', '+'))
        song_search_res_json = str(requests.get(song_search_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'}).text)
        song_search_res_json = song_search_res_json[song_search_res_json.rindex('data: "')+7:song_search_res_json.rindex('}"')+1]#.replace('\\', '')
        song_search_res_json = song_search_res_json.replace(r'\\"', '\x1a')  # replace \\" with substitute
        song_search_res_json = song_search_res_json.replace('\\', '')  # remove all \
        song_search_res_json = song_search_res_json.replace('\x1a', r'\"')  # replace substitute with \"
        song_search_res = json.loads(song_search_res_json)
        top_result_idx = 0 if 'musicShelfRenderer' in song_search_res['contents']['sectionListRenderer']['contents'][0] else 1
        if 'watchEndpoint' in song_search_res['contents']['sectionListRenderer']['contents'][top_result_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['doubleTapCommand'] and song_search_res['contents']['sectionListRenderer']['contents'][top_result_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['doubleTapCommand']['watchEndpoint']['watchEndpointMusicSupportedConfigs']['watchEndpointMusicConfig']['musicVideoType'] == 'MUSIC_VIDEO_TYPE_ATV':
            print('{} top result is a SONG'.format(track))
            song_url = 'https://music.youtube.com/watch?v={}'.format(song_search_res['contents']['sectionListRenderer']['contents'][0]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['doubleTapCommand']['watchEndpoint']['videoId'])
        else:
            print('{} top result is a NOT A SONG'.format(track))
            for i in range(1, len(song_search_res['contents']['sectionListRenderer']['contents'])):
                if song_search_res['contents']['sectionListRenderer']['contents'][i]['musicShelfRenderer']['title']['runs'][0]['text'] == 'Songs':
                    songs_idx = i
                    break
            else:
                songs_idx = None
            song_url = 'https://music.youtube.com/watch?v={}'.format(song_search_res['contents']['sectionListRenderer']['contents'][songs_idx]['musicShelfRenderer']['contents'][0]['musicResponsiveListItemRenderer']['doubleTapCommand']['watchEndpoint']['videoId'])
        return song_url
    except:
        print(song_search_res_json)
        return None



def download_song(track, track_num, album_artist, album_artist_current, album_name, album_genre, album_year, album_artwork_path, downloads_path):
    for i in range(5):
        song_url = get_song_url(track, album_artist, album_name)
        if song_url:
            print('Song URL found (trial {}): {}'.format(i, track))
            break
        else:
            print('Song URL not found (trial {}): {}'.format(i, track))
    else:
        print('WARNING! Song will not be downloaded: {}'.format(track))
        return
    
    track_file = '{} {}'.format(str(track_num).zfill(2), track.replace(':', '').replace('?', '').replace('!', '').replace('"', ''))
    track_path = os.path.join(downloads_path, '{}.mp3'.format(track_file))
    
    print('Song: {} => {}'.format(track, song_url))
    os.system('youtube-dl -x --audio-format mp3 --audio-quality 0 -o "{}.%(ext)s" "{}"'.format(os.path.join(downloads_path, track_file), song_url))
    while not os.path.exists(track_path):
        print('Retrying... {} => {}'.format(track, song_url))
        os.system('youtube-dl -x --audio-format mp3 --audio-quality 0 -o "{}.%(ext)s" "{}"'.format(os.path.join(downloads_path, track_file), song_url))
    
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
    audiofile.tag.disc_num = 1

    if download_lyrics:
        print('Finding lyrics: {}'.format(track))
        for i in range(5):
            lyrics = get_lyrics(track, album_artist)
            if lyrics:
                print('Lyrics found (trial {}): {}'.format(i, track))
                audiofile.tag.lyrics.set(lyrics)
                break
            else:
                print('Lyrics not found (trial {}): {}'.format(i, track))
        else:
            print('WARNING! Lyrics will not be downloaded: {}'.format(track))
    audiofile.tag.save(encoding='utf-8', version=eyed3.id3.ID3_V2_4)


def main(album_url=None):
    if not album_url:
        album_url = input('Apple Music URL (https://music.apple.com/xxx) for the album: ')

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

    album_res = requests.get(album_url).text
    schema_start_string = '<script name="schema:music-album" type="application/ld+json">'
    schema_start_index = album_res.index(schema_start_string)
    album_schema = json.loads(album_res[schema_start_index + len(schema_start_string) : album_res.index('</script>', schema_start_index)])

    album_name = get_titlecase(album_schema['name'])
    album_track_count = len(album_schema['tracks'])
    album_year = int(album_schema['datePublished'][:4])
    album_artist = get_titlecase(album_schema['byArtist']['name'])
    album_artist_current = get_titlecase(album_schema['byArtist']['name'], True)
    album_genre = album_schema['genre'][0]
    album_tracks = [get_titlecase(track['name']) for track in album_schema['tracks']]

    print(album_name, album_artist, album_genre, album_track_count, album_year, album_tracks)

    artwork_start_str = '<source sizes="(min-width:740px) and (max-width:999px) 270px, (min-width:1000px) and (max-width:1319px) 300px,  500px" srcset="'
    artwork_start_idx = album_res.index(artwork_start_str)
    artwork_search_str = album_res[artwork_start_idx + len(artwork_start_str) : album_res.index('" height="300" width="300" alt role="presentation">', artwork_start_idx)]
    artwork_search_str = artwork_search_str[:artwork_search_str.index('1000w')]
    artwork_search_str = artwork_search_str[artwork_search_str.rindex(',')+1:]
    album_artwork_url = artwork_search_str.strip()
    print(artwork_search_str)

    print(album_artwork_url)
    webp_artwork_path = get_relative_path('cache', 'artwork', '{}-{}-{}.webp'.format(album_artist.replace(' ', '_'), album_name.replace(' ', '_'), album_year))
    album_artwork_path = get_relative_path('cache', 'artwork', '{}-{}-{}.png'.format(album_artist.replace(' ', '_'), album_name.replace(' ', '_'), album_year))
    if not os.path.exists(album_artwork_path):
        r = requests.get(album_artwork_url, stream=True)
        if r.status_code == 200:
            with open(webp_artwork_path, 'wb') as f:
                 r.raw.decode_content = True
                 shutil.copyfileobj(r.raw, f)
            dwebp(webp_artwork_path, album_artwork_path, '-o')
            os.remove(webp_artwork_path)
    
    thread_set = set()
    for idx, track in enumerate(album_tracks):
        print('Downloading "{}" (track {}/{})...'.format(track, idx+1, album_track_count))
        current_thread = Thread(target=download_song, args=(track, idx+1, album_artist, album_artist_current, album_name, album_genre, album_year, album_artwork_path, downloads_path))
        current_thread.start()
        #download_song(track, idx+1, album_artist, album_artist_current, album_name, album_genre, album_year, album_artwork_path, downloads_path)
        thread_set.add(current_thread)
    for thread in thread_set:
        thread.join()

    track_filenames = ['{} {}.mp3'.format(str(idx+1).zfill(2), track.replace(':', '').replace('?', '').replace('!', '').replace('"', '')) for idx, track in enumerate(album_tracks)]
    for track_filename in track_filenames:
        print('{} is complete!'.format(track_filename))
        os.replace(os.path.join(downloads_path, track_filename), os.path.join(itunes_add_path, track_filename))
    # sleep(5)
    # album_folder_path = os.path.join(itunes_path, 'iTunes Media', 'Music', album_artist, album_name)
    # for track_filename in track_filenames:
    #     track_path = os.path.join(album_folder_path, '1-' + track_filename)
    #     audiofile = eyed3.load(track_path)
    #     audiofile.tag.save(encoding='utf-8', version=eyed3.id3.ID3_V2_3)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
