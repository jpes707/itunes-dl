# itunes-dl

Automatic iTunes album downloader for Windows

## Features

* Does not download audio from music videos, which are generally poor quality; instead only uses YouTube Music official artist audios as sources - a significant improvement from generic YouTube to MP3 converters

* Lyrics (from Genius)

* Complete song metadata (artist, song names, genre, etc. from Apple Music)

* Album art (1000x1000 pixels from Apple Music, CURRENTLY ONLY SHOWS IN ITUNES)

* Highest allowable audio quality with VBR (from YouTube Music)

* Correct title casing for all songs, albums, etc.

## Installation

1. Clone the repository.

2. `pip install -r requirements.txt`.

3. Ensure the python `site-packages` folder is on PATH so the `youtube-dl` module can be called from the Command Prompt.

4. Add the repository folder to PATH.

5. If lyrics are desired, create a file in the directory called `genius-key.txt` and place a free Genius API key from `https://docs.genius.com/` in that file. If lyrics are not desired, modify the `itunes_dl.py` file and change the `download_lyrics` variable on line 20 to `False`.

## Usage

* Command Prompt: `itunes-dl <Apple Music album link>`

* Example: `itunes-dl https://music.apple.com/us/album/folklore/1524801260`
