# pylint: disable=W1401

import os
import sys
import eyed3
import json
import requests
import shutil
import re
import atexit
from titlecase import titlecase
from time import time
from threading import Thread

use_legacy_names = True

legacy_names = {'Kesha': 'Ke$ha', 'The Chicks': 'Dixie Chicks', 'Lady A': 'Lady Antebellum', 'Panic! At the Disco': 'Panic at the Disco'}


def get_relative_path(*args):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), *args)


def get_titlecase(s, override_legacy_rename=False):
    if not s:
        return ''
    s = s.replace('&amp;', 'and')
    feat_idx = s.find('\x28feat.')
    if feat_idx is not -1:
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


def download_song(track, track_num, album_artist, album_artist_current, album_name, album_genre, album_year, album_artwork_path, downloads_path):
    song_search_url = 'https://music.youtube.com/search?q={}'.format((track + '+' + album_artist).replace(' ', '+'))
    song_search_res = requests.get(song_search_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36'}).text
    song_search_res = song_search_res[song_search_res.index('videoId', song_search_res.index(r'\"text\":\"Songs\"'))+12:]
    song_url = 'https://music.youtube.com/watch?v={}'.format(song_search_res[:song_search_res.index(r'\"')])
    track_file = '{} {}'.format(str(track_num).zfill(2), track.replace(':', '').replace('?', '').replace('!', '').replace('"', ''))
    print('Song: {} => {}'.format(track, song_url))
    os.system('youtube-dl -x --audio-format mp3 --audio-quality 0 -o "{}.%(ext)s" "{}"'.format(os.path.join(downloads_path, track_file), song_url))
    audiofile = eyed3.load(os.path.join(downloads_path, '{}.mp3'.format(track_file)))
    if (audiofile.tag == None):
        audiofile.initTag()
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
    lyrics_search_url = 'https://google.com/search?q={}'.format((track + '+' + album_artist_current + '+lyrics+genius').replace(' ', '+'))
    lyrics_search_res = requests.get(lyrics_search_url).text
    lyrics_search_res = lyrics_search_res[lyrics_search_res.index('href="/url?q=')+13:]
    lyrics_url = lyrics_search_res[:lyrics_search_res.index('&amp;')]
    print('Lyrics: {} => {}'.format(track, lyrics_url))
    lyrics_res = requests.get(lyrics_url).text.replace('\u2005', ' ').replace('’', "'")
    lyrics_res = lyrics_res[lyrics_res.index('<div class="lyrics">'):]
    lyrics_res = lyrics_res[:lyrics_res.index('</div>')].replace('<strong>', '').replace('<i>', '').replace('<em>', '').replace('</strong>', '').replace('</i>', '').replace('</em>', '')
    lyrics = ''
    for match in re.finditer("[A-Za-z0-9,'\"\-()\!\?\.][A-Za-z0-9 ,'\"\-()\!\?\.]+(?=<)|^<br>$", lyrics_res, re.MULTILINE):
        s = match.group(0)
        if s == '<br>':
            if not lyrics[-2:] == '\n\n':
                lyrics += '\n'
        else:
            lyrics += s + '\n'
    lyrics = lyrics[:-1]
    audiofile.tag.lyrics.set(lyrics)
    audiofile.tag.save()


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
    split_arr = album_schema['description'].split(' · ')
    album_track_count = int(split_arr[2][:split_arr[2].index(' ')])
    album_year = int(split_arr[1])
    album_artist = get_titlecase(album_schema['byArtist']['name'])
    album_artist_current = get_titlecase(album_schema['byArtist']['name'], True)
    album_genre = album_schema['genre'][0]
    album_tracks = [get_titlecase(track['name']) for track in album_schema['tracks']]

    print(album_name, album_artist, album_genre, album_track_count, album_year, album_tracks)

    artwork_start_str = '<img class="media-artwork-v2__image" sizes="(min-width:740px) and (max-width:999px) 270px, (min-width:1000px) and (max-width:1319px) 300px,  500px" src="/assets/artwork/1x1.gif" srcset="'
    artwork_start_idx = album_res.index(artwork_start_str)
    artwork_search_str = album_res[artwork_start_idx + len(artwork_start_str) : album_res.index('" height="300" width="300" alt role="presentation">', artwork_start_idx)]
    artwork_search_str = artwork_search_str[:artwork_search_str.index('1000w')]
    artwork_search_str = artwork_search_str[artwork_search_str.rindex(',')+1:]
    album_artwork_url = artwork_search_str.strip()
    print(artwork_search_str)

    album_artwork_path = get_relative_path('cache', 'artwork', '{}-{}-{}.png'.format(album_artist.replace(' ', '_'), album_name.replace(' ', '_'), album_year))
    if not os.path.exists(album_artwork_path):
        r = requests.get(album_artwork_url, stream=True)
        if r.status_code == 200:
            with open(album_artwork_path, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)

    thread_set = set()
    for idx, track in enumerate(album_tracks):
        print('Downloading "{}" (track {}/{})...'.format(track, idx+1, album_track_count))
        current_thread = Thread(target=download_song, args=(track, idx+1, album_artist, album_artist_current, album_name, album_genre, album_year, album_artwork_path, downloads_path))
        current_thread.start()
        thread_set.add(current_thread)
    for thread in thread_set:
        thread.join()

    for idx, track in enumerate(album_tracks):
        track_filename = '{} {}.mp3'.format(str(idx+1).zfill(2), track.replace(':', '').replace('?', '').replace('!', '').replace('"', ''))
        os.replace(os.path.join(downloads_path, track_filename), os.path.join(itunes_add_path, track_filename))

if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
