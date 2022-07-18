from re import match as re_match, findall as re_findall
from threading import Thread, Event
from time import time
from math import ceil
from html import escape
from psutil import disk_usage, cpu_percent, swap_memory, cpu_count, virtual_memory, net_io_counters, boot_time
from requests import head as rhead
from urllib.request import urlopen
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import download_dict, download_dict_lock, STATUS_LIMIT, botStartTime, DOWNLOAD_DIR, dispatcher
from bot.helper.telegram_helper.button_build import ButtonMaker

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = " 𝗥𝗲𝗰𝗲𝗶𝘃𝗶𝗻𝗴 𝗙𝗶𝗹𝗲 𝗙𝗿𝗼𝗺 𝗦𝗲𝗿𝘃𝗲𝗿"
    STATUS_DOWNLOADING = " 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗙𝗶𝗹𝗲 𝗧𝗼 𝗦𝗲𝗿𝘃𝗲𝗿"
    STATUS_CLONING = " 𝗖𝗹𝗼𝗻𝗶𝗻𝗴 𝗙𝗶𝗹𝗲 𝗙𝗿𝗼𝗺 𝗚𝗼𝗼𝗴𝗹𝗲 / 𝗔𝗽𝗽𝗗𝗿𝗶𝘃𝗲 !"
    STATUS_WAITING = " 𝗪𝗮𝗶𝘁𝗶𝗻𝗴 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 𝗙𝗶𝗹𝗲"
    STATUS_FAILED = " 𝗢𝗼𝗽𝘀 𝗘𝗿𝗿𝗼𝗿"
    STATUS_PAUSE = " 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴 𝗣𝗮𝘂𝘀𝗲𝗱"
    STATUS_ARCHIVING = " 𝗙𝗶𝗹𝗲 𝗜𝘀 𝗔𝗿𝗰𝗵𝗶𝘃𝗶𝗻𝗴 / 𝗭𝗶𝗽𝗶𝗻𝗴"
    STATUS_EXTRACTING = " 𝗙𝗶𝗹𝗲 𝗜𝘀 𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 / 𝗨𝗻𝘇𝗶𝗽𝗶𝗻𝗴"
    STATUS_SPLITTING = " 𝗙𝗶𝗹𝗲 𝗦𝗽𝗹𝗶𝘁𝘁𝗶𝗻𝗴"
    STATUS_CHECKING = " 𝗦𝗲𝗮𝗿𝗰𝗵𝗶𝗻𝗴 𝗙𝗶𝗹𝗲"
    STATUS_SEEDING = " 𝗦𝗲𝗲𝗱𝗶𝗻𝗴 𝗙𝗶𝗹𝗲"

class EngineStatus:
    STATUS_ARIA = "Based on Localhost Engine"
    STATUS_GDRIVE = "Based on Google Engine"
    STATUS_MEGA = "Based on Mega Engine"
    STATUS_QB = "Based on Qbit Engine"
    STATUS_TG = "Based on Cloudflare Engine"
    STATUS_YT = "Based on Youtube Engine"
    STATUS_EXT = "Based on Java Engine"
    STATUS_SPLIT = "Based on Phython Engine"
    STATUS_ZIP = "Based on Java Engine"

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = Event()
        thread = Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time() + self.interval
        while not self.stopEvent.wait(nextTime - time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large Bro'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload(req_status: str):
    with download_dict_lock:
        for dl in list(download_dict.values()):
            status = dl.status()
            if status not in [MirrorStatus.STATUS_ARCHIVING, MirrorStatus.STATUS_EXTRACTING, MirrorStatus.STATUS_SPLITTING] and dl:
                if req_status == 'down' and (status not in [MirrorStatus.STATUS_SEEDING,
                                                            MirrorStatus.STATUS_UPLOADING,
                                                            MirrorStatus.STATUS_CLONING]):
                    return dl
                elif req_status == 'up' and status == MirrorStatus.STATUS_UPLOADING:
                    return dl
                elif req_status == 'clone' and status == MirrorStatus.STATUS_CLONING:
                    return dl
                elif req_status == 'seed' and status == MirrorStatus.STATUS_SEEDING:
                    return dl
                elif req_status == 'all':
                    return dl
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = '●' * cFull
    p_str += '○' * (12 - cFull)
    p_str = f" {p_str} "
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        if STATUS_LIMIT is not None:
            tasks = len(download_dict)
            global pages
            pages = ceil(tasks/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for index, download in enumerate(list(download_dict.values())[COUNT:], start=1):
            msg += f"<b> ● </b> <code>{escape(str(download.name()))}</code>"
            msg += f"\n<b>Status - </b> <i>{download.status()}</i>\n<b> Connected - </b> {download.eng()}"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n{get_progress_bar_string(download)} {download.progress()}"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"\n<b>Cloned - </b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"\n<b>Receiving - </b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                else:
                    msg += f"\n<b>Sending - </b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                msg += f"\n<b>Pro - </b> {download.speed()} - <b>ETA - </b> {download.eta()}"
                msg += f"\n<b>Elapsed - </b>{get_readable_time(time() - download.message.date.timestamp())}"
                msg += f"\n<b>Ai - </b> {download.eng()}"
                try:
                    msg += f"\n<b>SS - </b> {download.aria_download().num_seeders}" \
                           f" - <b>PS - </b> {download.aria_download().connections}"
                except:
                    pass
                try:
                    msg += f"\n<b>SS - </b> {download.torrent_info().num_seeds}" \
                           f" - <b>LS - </b> {download.torrent_info().num_leechs}"
                except:
                    pass
                if download.message.chat.type != 'private':
                    try:
                        chatid = str(download.message.chat.id)[4:]
                        msg += f'\n<b>Original </b><a href="https://t.me/c/{chatid}/{download.message.message_id}">{download.message.from_user.first_name}</a> <b>ID - </b> <code>{download.message.from_user.id}</code>'
                    except:
                        pass
                else:
                    msg += f'\n<b>Bro </b> ️<code>{download.message.from_user.first_name}</code> <b>ID - </b> <code>{download.message.from_user.id}</code>'
                msg += f"\n<b>Bot Rest - </b><code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"\n<b>Size - </b>{download.size()}"
                msg += f"\n<b>Pro - </b>{get_readable_file_size(download.torrent_info().upspeed)}/s"
                msg += f"\n<b>Ai - </b> {download.eng()}"
                msg += f" - <b>Receiving - </b>{get_readable_file_size(download.torrent_info().uploaded)}"
                msg += f"\n<b>Ratio - </b>{round(download.torrent_info().ratio, 3)}"
                msg += f" - <b>Time - </b>{get_readable_time(download.torrent_info().seeding_time)}"
                msg += f"\n<code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                msg += f"\n<b>Size - </b>{download.size()}"
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        bmsg = f"<b>C - </b> {cpu_percent()}  - <b>F - </b> {get_readable_file_size(disk_usage(DOWNLOAD_DIR).free)}"
        bmsg += f"\n<b>R - </b> {virtual_memory().percent}  - <b>UT - </b> {get_readable_time(time() - botStartTime)}"
        dlspeed_bytes = 0
        upspeed_bytes = 0
        for download in list(download_dict.values()):
            spd = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in spd:
                    dlspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'M' in spd:
                    dlspeed_bytes += float(spd.split('M')[0]) * 1048576
            elif download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in spd:
                    upspeed_bytes += float(spd.split('K')[0]) * 1024
                elif 'MB/s' in spd:
                    upspeed_bytes += float(spd.split('M')[0]) * 1048576
        bmsg += f"\n<b>SD ⥃ </b> {get_readable_file_size(dlspeed_bytes)}/s ⚡️ <b>RC ⥃ </b> {get_readable_file_size(upspeed_bytes)}/s"
        buttons = ButtonMaker()
        buttons.sbutton("Bot - Performance", str(FOUR))
        sbutton = InlineKeyboardMarkup(buttons.build_menu(1))
        if STATUS_LIMIT is not None and tasks > STATUS_LIMIT:
            buttons = ButtonMaker()
            buttons.sbutton(" ← ", "status ← ")
            buttons.sbutton(f"{PAGE_NO}/{pages}", str(THREE))
            buttons.sbutton(" → ", "status → ")
            buttons.sbutton("Bot - Performance", str(FOUR))
            button = InlineKeyboardMarkup(buttons.build_menu(3))
            return msg + bmsg, button
        return msg + bmsg, sbutton

def turn(data):
    try:
        with download_dict_lock:
            global COUNT, PAGE_NO
            if data[1] == " → ":
                if PAGE_NO == pages:
                    COUNT = 0
                    PAGE_NO = 1
                else:
                    COUNT += STATUS_LIMIT
                    PAGE_NO += 1
            elif data[1] == " ← ":
                if PAGE_NO == 1:
                    COUNT = STATUS_LIMIT * (pages - 1)
                    PAGE_NO = pages
                else:
                    COUNT -= STATUS_LIMIT
                    PAGE_NO -= 1
        return True
    except:
        return False

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re_findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re_match(r'https?://.+\.gdtot\.\S+', url)
    return bool(url)

def is_appdrive_link(url: str):
    url = re_match(r'https?://(?:\S*\.)?(?:appdrive|driveapp)\.in/\S+', url)
    return bool(url)
def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re_findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper

def get_content_type(link: str) -> str:
    try:
        res = rhead(link, allow_redirects=True, timeout=5, headers = {'user-agent': 'Wget/1.12'})
        content_type = res.headers.get('content-type')
    except:
        try:
            res = urlopen(link, timeout=5)
            info = res.info()
            content_type = info.get_content_type()
        except:
            content_type = None
    return content_type

ONE, TWO, THREE, FOUR = range(4)
def pop_up_stats(update, context):
    query = update.callback_query
    stats = bot_sys_stats()
    query.answer(text=stats, show_alert=True)
def bot_sys_stats():
    currentTime = get_readable_time(time() - botStartTime)
    cpu = cpu_percent(interval=0.5)
    memory = virtual_memory()
    mem_p = memory.percent
    total, used, free, disk = disk_usage('/')
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    sent = get_readable_file_size(net_io_counters().bytes_sent)
    recv = get_readable_file_size(net_io_counters().bytes_recv)
    num_active = 0
    num_upload = 0
    num_split = 0
    num_extract = 0
    num_archi = 0
    tasks = len(download_dict)
    for stats in list(download_dict.values()):
       if stats.status() == MirrorStatus.STATUS_DOWNLOADING:
                num_active += 1
       if stats.status() == MirrorStatus.STATUS_UPLOADING:
                num_upload += 1
       if stats.status() == MirrorStatus.STATUS_ARCHIVING:
                num_archi += 1
       if stats.status() == MirrorStatus.STATUS_EXTRACTING:
                num_extract += 1
       if stats.status() == MirrorStatus.STATUS_SPLITTING:
                num_split += 1
    stats = f"""
    {currentTime}\n
CPU - {cpu}  || RAM - {mem_p} \n
USED - {used} || FREE - {free}
SENT - {sent} || RECV - {recv}\n
Developer Jackssmit
SD - {num_active} ⥃ RC - {num_upload} ⥃ SPLIT - {num_split}
ZIP - {num_archi} ⥃ UNZIP - {num_extract} ⥃ TOTAL - {tasks} 
"""
    return stats
dispatcher.add_handler(
    CallbackQueryHandler(pop_up_stats, pattern="^" + str(FOUR) + "$")
)