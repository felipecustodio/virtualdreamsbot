# -*- coding: utf-8 -*-

"""vapor.py: Virtual Dreams Bot for Telegram. Generates Vaporwave music."""

__author__      = "Felipe S. Custódio"
__license__ = "GPL"
__credits__ = ["WJLiddy", "vivjay"]

# environment
import os
import sys
from threading import Thread
from pathlib import Path
from dotenv import load_dotenv
# bot
from functools import wraps
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.ext.dispatcher import run_async
from telegram import InlineQueryResultArticle, InputTextMessageContent, ChatAction
from emoji import emojize
# youtube search
import urllib.request
import urllib.parse
import re
# youtube downloader
import youtube_dl
# chorus finder
from pychorus import find_and_output_chorus
# logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# profiling
from timeit import default_timer as timer

# youtube urls for query parsing
youtube_urls = ('youtube.com', 'https://www.youtube.com/', 'http://www.youtube.com/', 'http://youtu.be/', 'https://youtu.be/', 'youtu.be')

# video duration limit
MAX_DURATION = 600  # seconds (10 minutes)

# fullwidth translation
HALFWIDTH_TO_FULLWIDTH = str.maketrans(
    '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!"#$%&()*+,-./:;<=>?@[]^_`{|}~',
    '０１２３４５６７８９ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ！゛＃＄％＆（）＊＋、ー。／：；〈＝〉？＠［］＾＿‘｛｜｝～')

# emojis
emoji_palm_tree = emojize(":palm_tree:", use_aliases=True)
emoji_video_camera = emojize(":video_camera:", use_aliases=True)
emoji_cd = emojize(":cd:", use_aliases=True)

# @felup.io (bot admin)
LIST_OF_ADMINS = [71491472]

def restricted(func):
    @wraps(func)
    def wrapped(bot, update, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in LIST_OF_ADMINS:
            logger.error("Unauthorized access denied for {}.".format(user_id))
            return
        return func(bot, update, *args, **kwargs)
    return wrapped

# typing function decorator
def send_upload_action(func):
    """Sends typing action while processing func command."""

    @wraps(func)
    def command_func(*args, **kwargs):
        bot, update = args
        bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.UPLOAD_AUDIO)
        func(bot, update, **kwargs)
    return command_func


def vapor(query, bot, request_id, chat_id):
    """Returns audio to the vapor command handler

    Searches YouTube for 'query', finds first match that has
    duration under the limit, download video with youtube_dl
    and extract .mp3 audio with ffmpeg. Extract chorus using
    pychorus. If it fails, try smaller chorus' times.
    Using sox, slow down and apply reverb. 
    Return vaporwaved audio.

    Query can be YouTube link. 
    """
    logger.info("[{}] Working on request.".format(str(request_id)))

    # check if query is youtube url
    logger.info("[{}] Searching for query.".format(str(request_id)))
    if not query.lower().startswith((youtube_urls)):
        # search for youtube videos matching query
        query_string = urllib.parse.urlencode({"search_query" : query})
        html_content = urllib.request.urlopen("http://www.youtube.com/results?" + query_string)
        search_results = re.findall(r'href=\"\/watch\?v=(.{11})', html_content.read().decode())
        # find video that fits max duration
        for url in search_results:
            # check for video duration
            info = youtube_dl.YoutubeDL().extract_info(url,download = False)
            full_title = info['title']
            if (info['duration'] < MAX_DURATION):
                # get first video that fits the limit duration
                break
            else:
                url = False                
        # if we ran out of urls, return error
        if (not url):
            raise ValueError('Could not find video that fits the maximum duration for ' + str(full_title) + '.')
    # query was a youtube link
    else:
        url = query    
        info = youtube_dl.YoutubeDL().extract_info(url,download = False)

    title = (re.sub(r'\W+', '', info['title']))[:15]  # cleanup title
    title = str((title.encode('ascii',errors='ignore')).decode())  # remove non-ascii characters

    # check if cached audio exists
    vapor_path = Path(title + "_vapor.wav")
    if vapor_path.is_file():
        logger.info("[{}] Found {} cached.".format(str(request_id), str(vapor_path)))
        vapor_path = title + "_vapor.wav"
        bot.send_audio(chat_id=chat_id, audio=open(vapor_path, 'rb'))
        return 

    # download video and extract mp3 audio
    logger.info("[{}] Downloading video and converting to mp3.".format(str(request_id)))
    ydl_opts = {
        'quiet': 'True',
        'format': 'bestaudio/best',
        'outtmpl': str(request_id) +'.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # prepare audio files paths
    audio_filename = str(request_id) + ".mp3"
    chorus_path = str(request_id) + "_chorus.wav"
    slow_path = str(request_id) + "_slow.wav"
    vapor_path = title + "_vapor.wav"

    # find and extract music chorus
    logger.info("[{}] Searching for song chorus.".format(str(request_id)))
    chorus = False
    chorus_duration = 15
    while (not chorus and chorus_duration > 0):
        chorus = find_and_output_chorus(audio_filename, chorus_path, 15)
        chorus_duration -= 5
    
    if (not chorus):
        try:
            os.remove(audio_filename)
            os.remove(chorus_path)
            os.remove(slow_path)
        except OSError:
            pass
        raise ValueError('Could not find chorus of ' + str(full_title) + '.')

    # slow down music
    logger.info("[{}] Applying Vaporwave FX.".format(str(request_id)))
    cmd = "sox −V0 -v 0.99 " + chorus_path + " " + slow_path + " speed " + str(0.63)
    os.system(cmd)
    # vapor music
    cmd = "sox −V0 -v 0.99 " + slow_path + " " + vapor_path + " reverb 100"
    os.system(cmd)

    # send audio to user
    logger.info("[{}] Sending audio.".format(str(request_id), ))
    vapor_path = title + "_vapor.wav"
    bot.send_audio(chat_id=chat_id, audio=open(vapor_path, 'rb'))

    # check if cache size is big and warn admin
    cache_size = sum(os.path.getsize(f) for f in os.listdir('.') if os.path.isfile(f)) * 0.000001
    logger.info("[{}] Current cache size: {}".format(str(request_id), str(cache_size)))
    if (cache_size > 500):
        logger.info("Warning admin about cache size.")
        bot.send_message(chat_id=LIST_OF_ADMINS[0], text=emoji_cd + " Cache is over 500MB! Bot needs restart.")

    # cleanup
    logger.info("[{}] Cleanup temporary files.".format(str(request_id), ))
    try:
        os.remove(audio_filename)
        os.remove(chorus_path)
        os.remove(slow_path)
    except OSError:
        pass


# bot handlers
@restricted
def test_command(bot, update):
    """ Test if bot is alive (returns True for CI) """
    bot.send_message(chat_id=LIST_OF_ADMINS[0], text=emoji_palm_tree + " Virtual Dreams is ONLINE.")
    return True


@run_async
def help_command(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text=emoji_palm_tree + " Ｗｅｌｃｏｍｅ ｔｏ Ｖｉｒｔｕａｌ Ｄｒｅａｍｓ. " + emoji_palm_tree + "\n\nＨＯＷ ＴＯ ＵＳＥ:\n" + emoji_cd + " /vapor \"song name\"\n" + emoji_video_camera + " /vapor YouTube URL.")


@run_async
@send_upload_action
def vapor_command(bot, update):
    request_id = update.message.message_id
    chat_id = update.message.chat_id
    logger.info("[{}] {} has requested{}".format(str(request_id), str(update.message.from_user.username), update.message.text.replace('/vapor','')))

    if (len(str(update.message.text.replace('/vapor',''))) < 5):
        logger.error("[{}] ERROR: Query too small.".format(request_id))
        bot.send_message(chat_id=chat_id, text=emoji_cd + " ＥＲＲＯＲ.\nI need a bigger query!")
        return

    bot.send_message(chat_id=chat_id, text=emoji_palm_tree  + " ＷＯＲＫＩＮＧ．．．\nThis can take up a bit more than a minute. Sit back and relax.")
    try:
        start = timer()
        vapor(update.message.text.replace('/vapor',''), bot, request_id, chat_id)
    except ValueError as error:
        logger.error("[{}] ERROR: {}".format(request_id, str(error)))
        bot.send_message(chat_id=chat_id, text=emoji_cd + " ＥＲＲＯＲ.\n" + str(error))
    finally:
        end = timer()
        logger.info("[{}] Finished request in {}s.".format(str(request_id), str(end - start)))


@run_async
def unknown_command(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text=emoji_cd + " ＥＲＲＯＲ.\nThis is not a valid command. Use /help to find out more.")


def main():
    # bot initialize
    load_dotenv()
    BOT_TOKEN = os.getenv("TOKEN")
    updater = Updater(token=BOT_TOKEN)
    dispatcher = updater.dispatcher

    def stop_and_restart():
        """ Clear cache """
        for filename in os.listdir():
            if filename.endswith(('.mp3', '.wav')):
                os.remove(filename)
        os.chdir("..")
        
        """Gracefully stop the Updater and replace the current process with a new one"""
        updater.stop()
        os.execl(sys.executable, sys.executable, *sys.argv)

    @restricted
    def restart(bot, update):
        update.message.reply_text('Bot is restarting...')
        Thread(target=stop_and_restart).start()

    # define bot handlers
    help_handler = CommandHandler('help', help_command)
    start_handler = CommandHandler('start', help_command)
    vapor_handler = CommandHandler('vapor', vapor_command)
    test_handler = CommandHandler('test', test_command)
    restart_handler = CommandHandler('restart', restart)
    unknown_handler = MessageHandler(Filters.command, unknown_command)

    # start bot handlers
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(vapor_handler)
    dispatcher.add_handler(test_handler)
    dispatcher.add_handler(restart_handler)
    dispatcher.add_handler(unknown_handler)

    # move working directory to cache
    if not os.path.exists("cache") and not (str(os.path.basename(os.getcwd())) == "cache"):
        try:
            os.makedirs("cache")
            os.chdir("cache")
        except:
            raise
    else:
        os.chdir("cache")

    updater.start_polling()
    print("[BOT] Bot ready. Directory: {}".format(str(os.getcwd())))
    updater.idle()
    

if __name__ == '__main__':
    main()
