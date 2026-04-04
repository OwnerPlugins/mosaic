#!/usr/bin/python
# -*- coding: utf-8 -*-

# Mosaic by AliAbdul
# new screens (4/9 switchable) recalculated for hd/fhd by mrvica
# recoded from lululla 20240919 reference channel shot and add console
# recoded from lululla 20250519
# PicLoader - fix screen resize - play service in to screen
# clean code unused - refactoring  - skin  fix

from enigma import (
    ePicLoad,
    eServiceCenter,
    eServiceReference,
    getDesktop,
    eTimer
)
from Components.ActionMap import NumberActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.VideoWindow import VideoWindow
from Components.config import ConfigInteger, ConfigSubsection, config, ConfigText
from Plugins.Plugin import PluginDescriptor
from Screens.ChannelSelection import BouquetSelector
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.Setup import Setup

from os import makedirs, remove, listdir
from os.path import isfile, join, exists
from re import compile, sub, DOTALL
from sys import stdout
from time import sleep
from unicodedata import category, normalize
from urllib.parse import quote, unquote
from threading import Lock

from . import _
from .Console import Console as MyConsole
from .PicLoader import PicLoader, AVSwitch


global firstscrennshot
firstscrennshot = True

grab_binary = "/usr/bin/grab"
grab_errorlog = "/tmp/mosaic.log"
SCREENSHOT_DIR = "/tmp/mosaic_screenshots"

config_limits = (3, 30)
config.plugins.Mosaic = ConfigSubsection()
config.plugins.Mosaic.countdown = ConfigInteger(
    default=5, limits=config_limits)
config.plugins.Mosaic.howmanyscreens = ConfigInteger(default=9)
config.plugins.Mosaic.userfolder = ConfigText(
    default=SCREENSHOT_DIR, fixed_size=False)

plugin_name = "Mosaic"
plugin_description = "Mosaic 9/4 Screens"
plugin_icon = 'icon.png'

# Create screenshot directory if not exists
if not exists(SCREENSHOT_DIR):
    makedirs(SCREENSHOT_DIR)


def isFHD():
    try:
        return getDesktop(0).size().width() > 1280
    except BaseException:
        return False


def getScale():
    return AVSwitch().getFramebufferScale()


# --- Complex regex pattern for removing noisy parts from titles ---
REGEX = compile(
    r'[\(\[].*?[\)\]]|'                    # Round or square brackets
    r':?\s?odc\.\d+|'                      # "odc." optionally prefixed
    r'\d+\s?:?\s?odc\.\d+|'                # Number followed by "odc."
    r'[:!]|'                               # Colon or exclamation mark
    r'\s-\s.*|'                            # Dash followed by text
    r',|'                                  # Comma
    r'/.*|'                                # Slash and everything after
    r'\|\s?\d+\+|'                         # Pipe followed by number+
    r'\d+\+|'                              # Number followed by plus
    r'\s\*\d{4}\Z|'                        # * followed by 4-digit year
    r'[\(\[\|].*?[\)\]\|]|'                # Brackets or pipe with content
    r'(?:\"[\.|\,]?\s.*|\"|'               # Text inside quotes
    r'\.\s.+)|'                            # Dot followed by text
    r'Премьера\.\s|'                       # Russian: "Premiere."
    r'[хмтдХМТД]/[фс]\s|'                  # Russian patterns /ф /с
    r'\s[сС](?:езон|ерия|-н|-я)\s.*|'      # Season or episode (RU)
    r'\s\d{1,3}\s[чсЧС]\.?\s.*|'           # Part/episode number (RU)
    r'\.\s\d{1,3}\s[чсЧС]\.?\s.*|'         # Same with leading dot
    r'\s[чсЧС]\.?\s\d{1,3}.*|'             # Marker then number (RU)
    r'\d{1,3}-(?:я|й)\s?с-н.*', DOTALL     # Ends with Russian suffix
)


def cutName(eventName=""):
    """
    Remove known unwanted patterns from event titles.
    """
    if not eventName:
        return ""

    patterns = [
        '"', 'Х/Ф', 'М/Ф', 'Х/ф', '.', ' | ',
        '(18+)', '18+', '(16+)', '16+', '(12+)', '12+',
        '(7+)', '7+', '(6+)', '6+', '(0+)', '0+', '+',
        'episode', 'مسلسل', 'فيلم وثائقى', 'حفل'
    ]

    for pattern in patterns:
        eventName = eventName.replace(pattern, "")
    return eventName


def getCleanTitle(eventTitle=""):
    """
    Remove specific symbols from custom tags used in the system.
    """
    if not eventTitle:
        return ""
    return eventTitle.replace(" ^`^s", "").replace(" ^`^y", "")


def remove_accents(string):
    """
    Remove diacritic marks from characters (e.g., accents).
    """
    if not isinstance(string, str):
        string = str(string, "utf-8")
    string = normalize("NFD", string)
    return "".join(char for char in string if category(char) != "Mn")


def dataenc(data):
    """
    Ensure UTF-8 encoding based on Python version.
    """
    data = data.decode("utf-8")
    return data


def clean_filename(title):
    """
    Sanitize title for use as a valid filename.
    Handles special characters, accents, and empty titles.

    Returns:
        str: Cleaned filename or "no_title"
    """
    if not title:
        return "no_title"

    if not isinstance(title, (str, bytes)):
        try:
            title = str(title)
        except Exception:
            return "no_title"

    try:
        if isinstance(title, bytes):
            title = title.decode("utf-8", errors="ignore")

        original_title = title

        try:
            title = normalize("NFKD", title)
            title = title.encode("ascii", "ignore").decode("ascii")
            if not title.strip():
                title = original_title
        except Exception:
            title = original_title

        title = sub(r"[^\w\s-]", "_", title)
        title = sub(r"[\s-]+", "_", title)
        title = sub(r"_+", "_", title)
        title = title.strip("_")

        clean_title = title.lower()[:100]
        return clean_title if clean_title else "no_title"

    except Exception:
        return "no_title"


def convtext(text=""):
    """
    Clean and normalize text for consistent comparison or use as filename.
    Converts to lowercase, removes accents, unwanted patterns, and encodes safely.

    Args:
        text (str): Input text to clean.

    Returns:
        str: Cleaned and normalized string.
    """
    try:
        if text and text.lower() != "none":
            print("Original text:", text)
            text = text.lower()
            text = remove_accents(text)
            text = cutName(text)
            text = getCleanTitle(text)
            text = text.replace(" ", "")
            text = text.strip(" -").strip(" ")
            text = quote(text, safe="")

            # Apply filename sanitization
            text = clean_filename(text)

        return unquote(text)
    except Exception as e:
        print("convtext error:", e)
        return unquote(text)


class MosaicSettings(Setup):
    def __init__(self, session, parent=None):
        Setup.__init__(
            self,
            session,
            setup="MosaicSettings",
            plugin="Extensions/mosaic")
        self.parent = parent

    def keySave(self):
        Setup.keySave(self)


class Mosaic(Screen):

    PLAY = 0
    PAUSE = 1

    global windowWidth, windowHeight

    desktop = getDesktop(0)
    size = desktop.size()
    width = size.width()
    height = size.height()

    if isFHD:
        if config.plugins.Mosaic.howmanyscreens.value == 9:
            windowWidth = width / 4 + 102
            windowHeight = height / 4 + 30
            positions = []
            x = 45
            y = 45
            for i in range(1, 10):
                positions.append([x, y])
                x += windowWidth
                x += ((width - 81) - (windowWidth * 3)) / 2
                if (i == 3) or (i == 6):
                    y = y + windowHeight + 45
                    x = 45
        else:
            windowWidth = width / 2 - 75    # 885
            windowHeight = height / 2 - 68   # 473
            positions = []
            x = 45
            y = 45
            for i in range(1, 5):
                positions.append([x, y])
                x += windowWidth
                x += ((width - 90) - (windowWidth * 2))
                if (i == 2):
                    y = y + windowHeight + 45
                    x = 45
    else:
        if config.plugins.Mosaic.howmanyscreens.value == 9:
            windowWidth = width / 4 + 68
            windowHeight = height / 4 + 20
            positions = []
            x = 30
            y = 30
            for i in range(1, 10):
                positions.append([x, y])
                x += windowWidth
                x += ((width - 54) - (windowWidth * 3)) / 2
                if (i == 3) or (i == 6):
                    y = y + windowHeight + 30
                    x = 30
        else:
            windowWidth = width / 2 - 50    # 590
            windowHeight = height / 2 - 45  # 315
            positions = []
            x = 30
            y = 30
            for i in range(1, 5):
                positions.append([x, y])
                x += windowWidth
                x += ((width - 60) - (windowWidth * 2))
                if (i == 2):
                    y = y + windowHeight + 30
                    x = 30

    if isFHD:
        if config.plugins.Mosaic.howmanyscreens.value == 9:
            skin = ""
            skin += """<screen position="0,0" size="%d,%d" title="Mosaic" flags="wfNoBorder" backgroundColor="#ffffff" >""" % (
                width, height)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[4][0] - 3, positions[4][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[5][0] - 3, positions[5][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[6][0] - 3, positions[6][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[7][0] - 3, positions[7][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[8][0] - 3, positions[8][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="channel1" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[0][0], positions[0][1] - 33, windowWidth - 6)
            skin += """<widget name="channel2" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[1][0], positions[1][1] - 33, windowWidth - 6)
            skin += """<widget name="channel3" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[2][0], positions[2][1] - 33, windowWidth - 6)
            skin += """<widget name="channel4" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[3][0], positions[3][1] - 33, windowWidth - 6)
            skin += """<widget name="channel5" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[4][0], positions[4][1] - 33, windowWidth - 6)
            skin += """<widget name="channel6" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[5][0], positions[5][1] - 33, windowWidth - 6)
            skin += """<widget name="channel7" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[6][0], positions[6][1] - 33, windowWidth - 6)
            skin += """<widget name="channel8" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[7][0], positions[7][1] - 33, windowWidth - 6)
            skin += """<widget name="channel9" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[8][0], positions[8][1] - 33, windowWidth - 6)
            skin += """<widget name="window1" scale="1" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window2" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window3" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window4" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window5" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[4][0] - 3, positions[4][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window6" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[5][0] - 3, positions[5][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window7" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[6][0] - 3, positions[6][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window8" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[7][0] - 3, positions[7][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window9" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[8][0] - 3, positions[8][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video1" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video2" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video3" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video4" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video5" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[4][0] - 3, positions[4][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video6" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[5][0] - 3, positions[5][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video7" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[6][0] - 3, positions[6][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video8" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[7][0] - 3, positions[7][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video9" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[8][0] - 3, positions[8][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="event1" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth)
            skin += """<widget name="event2" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth)
            skin += """<widget name="event3" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth)
            skin += """<widget name="event4" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth)
            skin += """<widget name="event5" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[4][0] - 3, positions[4][1] - 2, windowWidth)
            skin += """<widget name="event6" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[5][0] - 3, positions[5][1] - 2, windowWidth)
            skin += """<widget name="event7" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[6][0] - 3, positions[6][1] - 2, windowWidth)
            skin += """<widget name="event8" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[7][0] - 3, positions[7][1] - 2, windowWidth)
            skin += """<widget name="event9" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[8][0] - 3, positions[8][1] - 2, windowWidth)
            skin += """<widget name="countdown" position="45,%d" size="200,30" font="Regular;27" zPosition="4" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                height - 45)  # , windowWidth)

            skin += """<eLabel backgroundColor="#8c8c8c" cornerRadius="30" position="472,1032" zPosition="2" size="970,45" />"""
            skin += """<eLabel position="690,1035" size="40,40" font="Regular;36" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#0000ff00" text=">"/>"""
            skin += """<eLabel position="750,1035" size="40,40" font="Regular;36" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#00ffa000" text="||"/>"""
            skin += """<widget render="Label" source="key_blue" position="865,1035" size="140,40" zPosition="5" font="Regular;34" halign="center" valign="center" backgroundColor="#18188b" transparent="1" />"""
            skin += """<widget name="blue" position="810,1035" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/blue.png" zPosition="5" alphatest="on" />"""
            skin += """<widget render="Label" source="key_yellow" position="1085,1035" size="140,40" zPosition="5" font="Regular;34" halign="center" valign="center" backgroundColor="#a08500" transparent="1" />"""
            skin += """<widget name="yellow" position="1030,1035" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/yellow.png" zPosition="5" alphatest="on" />"""

            skin += """<widget name="count" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" halign="right" />
            </screen>""" % (positions[2][0], height - 45, windowWidth)
        else:
            skin = ""
            skin += """<screen position="0,0" size="%d,%d" title="Mosaic" flags="wfNoBorder" backgroundColor="#ffffff" >""" % (
                width, height)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="channel1" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[0][0], positions[0][1] - 33, windowWidth - 6)
            skin += """<widget name="channel2" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[1][0], positions[1][1] - 33, windowWidth - 6)
            skin += """<widget name="channel3" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[2][0], positions[2][1] - 33, windowWidth - 6)
            skin += """<widget name="channel4" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[3][0], positions[3][1] - 33, windowWidth - 6)
            skin += """<widget name="window1" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window2" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window3" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="window4" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video1" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video2" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video3" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="video4" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth, windowHeight)
            skin += """<widget name="event1" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[0][0] - 3, positions[0][1] - 2, windowWidth)
            skin += """<widget name="event2" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[1][0] - 3, positions[1][1] - 2, windowWidth)
            skin += """<widget name="event3" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[2][0] - 3, positions[2][1] - 2, windowWidth)
            skin += """<widget name="event4" position="%d,%d" size="%d,30" zPosition="3" font="Regular;26" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[3][0] - 3, positions[3][1] - 2, windowWidth)
            skin += """<widget name="countdown" position="45,%d" size="200,30" font="Regular;27" zPosition="4" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                height - 45)  # , windowWidth)

            skin += """<eLabel backgroundColor="#8c8c8c" cornerRadius="30" position="472,1032" zPosition="2" size="970,45" />"""
            skin += """<eLabel position="690,1035" size="40,40" font="Regular;36" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#0000ff00" text=">" />"""
            skin += """<eLabel position="750,1035" size="40,40" font="Regular;36" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#00ffa000" text="||" />"""
            skin += """<widget render="Label" source="key_blue" position="865,1035" size="140,40" zPosition="5" font="Regular;34" halign="center" valign="center" backgroundColor="#18188b" transparent="1" />"""
            skin += """<widget name="blue" position="810,1035" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/blue.png" zPosition="5" alphatest="on" />"""
            skin += """<widget render="Label" source="key_yellow" position="1085,1035" size="140,40" zPosition="5" font="Regular;34" halign="center" valign="center" backgroundColor="#a08500" transparent="1" />"""
            skin += """<widget name="yellow" position="1030,1035" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/yellow.png" zPosition="5" alphatest="on" />"""

            skin += """<widget name="count" position="%d,%d" size="%d,30" font="Regular;27" backgroundColor="#ffffff" foregroundColor="#000000" halign="right" />
            </screen>""" % (positions[2][0], height - 45, windowWidth + 945)

    else:
        if config.plugins.Mosaic.howmanyscreens.value == 9:
            skin = ""
            skin += """<screen position="0,0" size="%d,%d" title="Mosaic" flags="wfNoBorder" backgroundColor="#ffffff" >""" % (
                width, height)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[4][0] - 2, positions[4][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[5][0] - 2, positions[5][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[6][0] - 2, positions[6][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[7][0] - 2, positions[7][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[8][0] - 2, positions[8][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="channel1" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[0][0], positions[0][1] - 22, windowWidth - 4)
            skin += """<widget name="channel2" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[1][0], positions[1][1] - 22, windowWidth - 4)
            skin += """<widget name="channel3" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[2][0], positions[2][1] - 22, windowWidth - 4)
            skin += """<widget name="channel4" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[3][0], positions[3][1] - 22, windowWidth - 4)
            skin += """<widget name="channel5" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[4][0], positions[4][1] - 22, windowWidth - 4)
            skin += """<widget name="channel6" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[5][0], positions[5][1] - 22, windowWidth - 4)
            skin += """<widget name="channel7" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[6][0], positions[6][1] - 22, windowWidth - 4)
            skin += """<widget name="channel8" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[7][0], positions[7][1] - 22, windowWidth - 4)
            skin += """<widget name="channel9" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[8][0], positions[8][1] - 22, windowWidth - 4)
            skin += """<widget name="window1" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window2" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window3" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window4" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window5" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[4][0] - 2, positions[4][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window6" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[5][0] - 2, positions[5][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window7" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[6][0] - 2, positions[6][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window8" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[7][0] - 2, positions[7][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window9" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[8][0] - 2, positions[8][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video1" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video2" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video3" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video4" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video5" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[4][0] - 2, positions[4][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video6" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[5][0] - 2, positions[5][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video7" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[6][0] - 2, positions[6][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video8" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[7][0] - 2, positions[7][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video9" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[8][0] - 2, positions[8][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="event1" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth)
            skin += """<widget name="event2" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth)
            skin += """<widget name="event3" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth)
            skin += """<widget name="event4" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth)
            skin += """<widget name="event5" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[4][0] - 2, positions[4][1] - 1, windowWidth)
            skin += """<widget name="event6" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[5][0] - 2, positions[5][1] - 1, windowWidth)
            skin += """<widget name="event7" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[6][0] - 2, positions[6][1] - 1, windowWidth)
            skin += """<widget name="event8" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[7][0] - 2, positions[7][1] - 1, windowWidth)
            skin += """<widget name="event9" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[8][0] - 2, positions[8][1] - 1, windowWidth)
            skin += """<widget name="countdown" position="30,%d" size="200,20" font="Regular;18" zPosition="4" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                height - 30)  # , windowWidth)

            skin += """<eLabel backgroundColor="#8c8c8c" cornerRadius="30" position="222,675" zPosition="2" size="865,45" />"""
            skin += """<eLabel position="415,678" size="40,40" font="Regular;28" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#0000ff00" text=">" />"""
            skin += """<eLabel position="465,678" size="40,40" font="Regular;28" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#00ffa000" text="||" />"""
            skin += """<widget render="Label" source="key_blue" position="600,677" size="140,40" zPosition="4" font="Regular;28" halign="center" valign="center" backgroundColor="#18188b" transparent="1" />"""
            skin += """<widget name="blue" position="550,676" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/blue.png" zPosition="5" alphatest="on" />"""
            skin += """<widget render="Label" source="key_yellow" position="795,677" size="140,40" zPosition="4" font="Regular;28" halign="center" valign="center" backgroundColor="#a08500" transparent="1" />"""
            skin += """<widget name="yellow" position="748,676" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/yellow.png" zPosition="5" alphatest="on" />"""
            skin += """<widget name="count" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" halign="right" />
            </screen>""" % (positions[2][0], height - 30, windowWidth)
        else:
            skin = ""
            skin += """<screen position="0,0" size="%d,%d" title="Mosaic" flags="wfNoBorder" backgroundColor="#ffffff" >""" % (
                width, height)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth, windowHeight)
            skin += """<eLabel position="%d,%d" size="%d,%d" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="channel1" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[0][0], positions[0][1] - 22, windowWidth - 4)
            skin += """<widget name="channel2" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[1][0], positions[1][1] - 22, windowWidth - 4)
            skin += """<widget name="channel3" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[2][0], positions[2][1] - 22, windowWidth - 4)
            skin += """<widget name="channel4" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                positions[3][0], positions[3][1] - 22, windowWidth - 4)
            skin += """<widget name="window1" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window2" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window3" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="window4" scale="stretch" position="%d,%d" zPosition="1" size="%d,%d" borderWidth="3" transparent="1" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video1" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video2" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video3" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="video4" position="%d,%d" zPosition="2" size="%d,%d" backgroundColor="#ffffffff" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth, windowHeight)
            skin += """<widget name="event1" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[0][0] - 2, positions[0][1] - 1, windowWidth)
            skin += """<widget name="event2" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[1][0] - 2, positions[1][1] - 1, windowWidth)
            skin += """<widget name="event3" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[2][0] - 2, positions[2][1] - 1, windowWidth)
            skin += """<widget name="event4" position="%d,%d" size="%d,20" zPosition="3" font="Regular;18" backgroundColor="#000000" foregroundColor="#ffffff" />""" % (
                positions[3][0] - 2, positions[3][1] - 1, windowWidth)
            skin += """<widget name="countdown" position="30,%d" size="200,20" font="Regular;18" zPosition="4" backgroundColor="#ffffff" foregroundColor="#000000" />""" % (
                height - 30)  # , windowWidth)

            skin += """<eLabel backgroundColor="#8c8c8c" cornerRadius="30" position="222,675" zPosition="2" size="865,45" />"""
            skin += """<eLabel position="415,678" size="40,40" font="Regular;32" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#0000ff00" text=">" />"""
            skin += """<eLabel position="465,678" size="40,40" font="Regular;32" backgroundColor="#10808080" foregroundColor="#000000" borderWidth="1" zPosition="4" borderColor="#00ffa000" text="||" />"""
            skin += """<widget render="Label" source="key_blue" position="600,677" size="140,40" zPosition="4" font="Regular;28" halign="center" valign="center" backgroundColor="#18188b" transparent="1" />"""
            skin += """<widget name="blue" position="550,676" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/blue.png" zPosition="5" alphatest="on" />"""
            skin += """<widget render="Label" source="key_yellow" position="795,677" size="140,40" zPosition="4" font="Regular;28" halign="center" valign="center" backgroundColor="#a08500" transparent="1" />"""
            skin += """<widget name="yellow" position="748,676" size="46,46" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/mosaic/button/yellow.png" zPosition="5" alphatest="on" />"""
            skin += """<widget name="count" position="%d,%d" size="%d,20" font="Regular;18" backgroundColor="#ffffff" foregroundColor="#000000" halign="right" />
            </screen>""" % (positions[2][0], height - 30, windowWidth + 630)

    def __init__(self, session, services):
        Screen.__init__(self, session)
        self.skin = Mosaic.skin
        print(f'[Mosaic] Initializing with skin: {self.skin}')
        self.session = session

        self.consoleCmd = ""
        self.grab_lock = Lock()
        self.MyConsoleCmd = ""
        self.MyConsole = MyConsole(self.session)
        self.serviceHandler = eServiceCenter.getInstance()
        self.ref_list = services

        # DEBUG: Verifica il tipo di services
        print(f"[Mosaic] Services type: {type(services)}")
        print(f"[Mosaic] Services count: {len(self.ref_list)}")

        # Inizializzazione attributi mancanti
        self.oldService = self.session.nav.getCurrentlyPlayingServiceReference()
        self.countdown = config.plugins.Mosaic.countdown.value
        self.howmanyscreens = config.plugins.Mosaic.howmanyscreens.value

        # Pagination setup
        self.max_windows = 9 if config.plugins.Mosaic.howmanyscreens.value == 9 else 4
        self.current_window = 1
        self.working = False
        self.state = self.PLAY
        self.window_refs = [None] * self.max_windows
        self.current_refidx = 0

        global firstscrennshot
        firstscrennshot = True

        self.idd = 0
        self._videoWindow = None
        self.windowWidth = windowWidth
        self.windowHeight = windowHeight
        for i in range(1, self.max_windows + 1):
            self["window" + str(i)] = Pixmap()
            self["video" + str(i)] = VideoWindow(decoder=0,
                                                 fb_width=self.width, fb_height=self.height)
            self["video" + str(i)].hide()
            self["channel" + str(i)] = Label("")
            self["event" + str(i)] = Label("")
            self["event" + str(i)].hide()

        self["video1"].decoder = 0
        self["video1"].show()
        self["countdown"] = Label()
        self["count"] = Label()
        self["blue"] = Pixmap()
        self["yellow"] = Pixmap()
        self["key_blue"] = Label(_("Switch 4/9"))
        self["key_yellow"] = Label(_("Pause"))
        self["actions"] = NumberActionMap(
            ["MosaicActions"],
            {
                "ok": self.exit,
                "cancel": self.closeWithOldService,
                "green": self.play,
                "yellow": self.pause,
                "blue": self.toggleScreens,
                "channelup": self.countdownPlus,
                "channeldown": self.countdownMinus,
                "displayHelp": self.showHelp,
                "menu": self.open_settings,
                "1": self.numberPressed,
                "2": self.numberPressed,
                "3": self.numberPressed,
                "4": self.numberPressed,
                "5": self.numberPressed,
                "6": self.numberPressed,
                "7": self.numberPressed,
                "8": self.numberPressed,
                "9": self.numberPressed
            },
            -1
        )

        self.PicLoad = ePicLoad()
        self.updateTimer = eTimer()
        self.updateTimer.callback.append(self.updateCountdown)

        self.checkTimer = eTimer()
        self.checkTimer.callback.append(self.checkGrab)
        self.checkTimer.start(500, True)
        self.onLayoutFinish.append(self.updateCountdownLabel)

    def isStandardMosaic(self):
        return self.__class__.__name__ == "Mosaic"

    def checkGrab(self):
        """Initialize first channel capture"""
        self.checkTimer.stop()  # Prevent re-entrancy
        try:
            # Play next ref
            ref = self.ref_list[self.current_refidx]
            self.window_refs[0] = ref
            info = self.serviceHandler.info(ref)
            name = info.getName(ref).replace(
                '\xc2\x86', '').replace(
                '\xc2\x87', '')
            event_name = self.getEventName(info)

            # first name screen
            self.name_name_grab = (convtext(name))
            print(
                f'[Mosaic] checkGrab name self.name_name_grab=:{str(self.name_name_grab)}')

            self["channel1"].setText(name)
            self["event1"].setText(event_name)
            self.session.nav.playService(ref)
            self["count"].setText("Channel: " + "1 / " +
                                  str(len(self.ref_list)))
            self.updateTimer.start(100, True)
        except Exception as e:
            print(f'[Mosaic] error checkGrab:{str(e)}')

    def name_grab(self):
        """ make show the service-name for next screen """
        ref = self.ref_list[self.current_refidx]
        info = self.serviceHandler.info(ref)
        name = info.getName(ref).replace(
            '\xc2\x86', '').replace(
            '\xc2\x87', '')
        self.name_name_grab = (convtext(name))
        return self.name_name_grab

    def exit(self, callback=None):
        self.deleteConsoleCallbacks()
        self.deletefilescreen()
        self.delete_all_screenshots()
        self.close()

    def closeWithOldService(self):
        try:
            self.session.nav.playService(self.oldService)
            self.deleteConsoleCallbacks()
            self.deletefilescreen()
            self.delete_all_screenshots()
            self.close()
        except BaseException:
            pass

    def delete_all_screenshots(self):
        from glob import glob
        self.directory = config.plugins.Mosaic.userfolder.value
        for path in glob(self.directory + "/*"):
            if isfile(path):
                try:
                    remove(path)
                except Exception as e:
                    print("[Mosaic] Failed to remove:", path, "-", str(e))

    def deletefilescreen(self):
        self.directory = '/tmp'
        pattern = compile(r'^[0-9]+.*')
        for filename in listdir(self.directory):
            if pattern.match(filename):
                file_path = join(self.directory, filename)
                if isfile(file_path):
                    remove(file_path)
                    print(f'[Mosaic] Rimosso {file_path}')

    def deleteConsoleCallbacks(self):
        if self.MyConsoleCmd in self.MyConsole.appContainers:
            try:
                del self.MyConsole.appContainers[self.MyConsoleCmd].dataAvail[:]
            except Exception as e:
                print(
                    f'[Mosaic] error del self.MyConsole.appContainers[self.MyConsoleCmd].dataAvail[:]{str(e)}')
            try:
                del self.MyConsole.appContainers[self.MyConsoleCmd].appClosed[:]
            except Exception as e:
                print(
                    f'[Mosaic] error self.MyConsole.appContainers[self.MyConsoleCmd].appClosed[:]{str(e)}')
            try:
                del self.MyConsole.appContainers[self.MyConsoleCmd]
            except Exception as e:
                print(
                    f'[Mosaic] error del self.MyConsole.appContainers[self.MyConsoleCmd]{str(e)}')
            try:
                del self.MyConsole.extra_args[self.MyConsoleCmd]
            except Exception as e:
                print(
                    f'[Mosaic] error del self.MyConsole.extra_args[self.MyConsoleCmd]{str(e)}')
            try:
                del self.MyConsole.callbacks[self.MyConsoleCmd]
            except Exception as e:
                print(
                    f'[Mosaic] error del self.MyConsole.callbacks[self.MyConsoleCmd] {str(e)}')

    # @property
    # def max_windows(self):
        # return self._max_windows

    def open_settings(self):
        self.session.open(MosaicSettings)

    def numberPressed(self, number):
        """Handle number key press"""
        if 1 <= number <= self.max_windows:
            print(f'[Mosaic] Number {number} pressed')
            self.current_window = number
            self._highlight_selected_window(number)
            self._switch_to_window(number)

    def _highlight_selected_window(self, number):
        """Highlight selected window"""
        for i in range(1, self.max_windows + 1):
            border = 3 if i == number else 0
            self[f"window{i}"].instance.setBorderWidth(border)

    def _switch_to_window(self, number):
        if self.window_refs[number - 1]:
            ref = self.window_refs[number - 1]

            # Hide all video widgets
            for i in range(1, self.max_windows + 1):
                self["video" + str(i)].hide()

            # Stop the current service
            self.session.nav.stopService()

            # Start the new service
            self.session.nav.playService(ref)

            # Retrieve video widget
            video_widget = self["video" + str(number)]
            """
            # Force position and size (read by skin)
            pos = video_widget.instance.position()
            size = video_widget.instance.size()
            video_widget.instance.move(pos)
            video_widget.instance.resize(size)
            """
            # Force resizing according to skin settings
            size = self["window" + str(number)].instance.size()
            pos = self["window" + str(number)].instance.position()

            video_widget.instance.resize(size)
            video_widget.instance.move(pos)

            # Show widget (after resize/move)
            video_widget.show()

            # Update info
            self._update_info_labels(number)

        print("DEBUG: Video {} attivato nel riquadro".format(number))

    def get_widget_position(self, widget_name):
        widget = self[widget_name]
        return (widget.instance.position().x(), widget.instance.position().y())

    def get_widget_size(self, widget_name):
        widget = self[widget_name]
        return (
            widget.instance.size().width(),
            widget.instance.size().height())

    def play(self):
        try:
            if self.working is False and self.state == self.PAUSE:
                self.state = self.PLAY
                self.updateTimer.start(1000, 1)
        except BaseException:
            pass

    def pause(self):
        try:
            if self.working is False and self.state == self.PLAY:
                self.state = self.PAUSE
                self.updateTimer.stop()
        except BaseException:
            pass

    def countdownPlus(self):
        """Increase countdown value by 1, within allowed limits."""
        try:
            self.changeCountdown(1)
        except Exception as e:
            self._log_error("Error in countdownPlus: %s" % str(e))

    def countdownMinus(self):
        """Decrease countdown value by 1, within allowed limits."""
        try:
            self.changeCountdown(-1)
        except Exception as e:
            self._log_error("Error in countdownMinus: %s" % str(e))

    def changeCountdown(self, direction):
        """
        Change the countdown configuration value by 'direction'.
        Enforces limits defined in config_limits.
        Updates the countdown label accordingly.
        """
        try:
            if not self.working:
                configNow = config.plugins.Mosaic.countdown.value
                configNow += direction

                # Clamp the value within the allowed limits
                if configNow < config_limits[0]:
                    configNow = config_limits[0]
                elif configNow > config_limits[1]:
                    configNow = config_limits[1]

                config.plugins.Mosaic.countdown.value = configNow
                config.plugins.Mosaic.countdown.save()

                self.updateCountdownLabel()

        except Exception as e:
            self._log_error("Error in changeCountdown: %s" % str(e))

    def createSummary(self):
        return Mosaic

    def getCurrentServiceReference(self):
        print('[Mosaic] Returns the reference to the currently playing service')
        import NavigationInstance
        playingref = None
        if NavigationInstance.instance:
            playingref = NavigationInstance.instance.getCurrentlyPlayingServiceReference()
        return playingref

    def makeNextScreenshot(self):
        """Capture screenshot for specific window"""
        with self.grab_lock:
            try:
                print(
                    f'[Mosaic] makeNextScreenshot Capturing window {self.current_window}')
                global firstscrennshot
                self.namepic = ''
                print(f'[Mosaic] firstscrennshot= {firstscrennshot}')
                if firstscrennshot:
                    self.idd = 0
                    firstscrennshot = False
                    self.namepic = str(
                        self.idd) + self.name_name_grab  # self.name_grab()
                else:
                    self.idd += 1
                    self.namepic = str(self.idd) + self.name_next_grab
                print(f'[Mosaic] name_grab= {self.name_grab}')

                # Hide all screen window
                self.hide()

                current_service_ref = self.getCurrentServiceReference()
                print(
                    f'[Mosaic] makeNextScreenshot current_service_ref {current_service_ref}')
                if current_service_ref:
                    service_ref = current_service_ref.toString()
                    print(
                        f'[Mosaic] makeNextScreenshot service_ref {service_ref}')

                    """Imposta il canale specifico - Fa uno screenshot del canale specificato."""
                    service = eServiceReference(service_ref)
                    self.session.nav.playService(service)

                sleep(3)

                print(f'[Mosaic] makeNextScreenshot namepic {self.namepic}')
                print(
                    f'[Mosaic] Width screen -r %d self.windowWidth= {self.windowWidth}')
                path_screenshots = config.plugins.Mosaic.userfolder.value
                self.consoleCmd = "%s -v -q -r %d -p %s/%s.png" % (
                    path_screenshots, grab_binary, self.windowWidth, self.namepic)
                print(f'[Mosaic] self.consoleCmd={self.consoleCmd}')
                self.MyConsole.ePopen(self.consoleCmd, self.showNextScreenshot)

            except Exception as e:
                print(f'[Mosaic] Error in makeNextScreenshot: {str(e)}')

    def showNextScreenshot(self, result, retval, extra_args):
        """Handle captured screenshot"""
        try:
            if retval == 0:
                """ Screenshot filename returned from the grab process """
                print(
                    f'[Mosaic] showNextScreenshot extra_args Screenshot filename returned from the grab process {extra_args}')
                self.picx = extra_args

                """ Load the screenshot and scale it to fit the corresponding window widget """
                # Create PicLoader instance
                picloader = PicLoader()
                widget = self["window" + str(self.current_window)]
                width = widget.instance.size().width()
                height = widget.instance.size().height()
                # Set target size for image
                picloader.setSize(width, height)
                # Load the image
                ptr = picloader.load(self.picx)
                # If the image was loaded, display it in the widget
                if ptr is not None:
                    widget.instance.setPixmap(ptr)

                # Cleanup PicLoader
                picloader.destroy()
                # Show the entire screen (if hidden)
                self.show()

                # Move to the next channel index in the reference list
                self.current_refidx += 1
                if self.current_refidx > (len(self.ref_list) - 1):
                    self.current_refidx = 0  # Loop back to first channel

                # Get the reference and info of the next channel
                ref = self.ref_list[self.current_refidx]
                info = self.serviceHandler.info(ref)
                name = info.getName(ref).replace(
                    '\xc2\x86', '').replace(
                    '\xc2\x87', '')  # Clean channel name
                # Get current event (EPG) name
                event_name = self.getEventName(info)
                self.session.nav.playService(ref)     # Tune to the new service

                # Hide the video widget for the current window
                self["video" + str(self.current_window)].hide()
                # print(f'[Mosaic] showNextScreenshot str(self.current_window) {str(self.current_window)}')

                # Advance to the next window index (loop after 9 or 4)
                self.current_window += 1
                if config.plugins.Mosaic.howmanyscreens.value == 9:
                    if self.current_window > 9:
                        self.current_window = 1
                else:
                    if self.current_window > 4:
                        self.current_window = 1

                # Store the current service reference for this window
                self.window_refs[self.current_window - 1] = ref

                # Hide event label and set the event text
                self["event" + str(self.current_window)].hide()
                self["event" + str(self.current_window)].setText(event_name)

                # Show the video widget for the new window
                self["video" + str(self.current_window)].show()
                # Reset decoder index
                self["video" + str(self.current_window)].decoder = 0

                # Display the channel name
                # print(f'[Mosaic] Loading screenshot for window {self.current_window}')
                self["channel" + str(self.current_window)].setText(name)

                # Update counter text (e.g. Channel: 3 / 9)
                self["count"].setText(
                    "Channel: " + str(self.current_refidx + 1) + " / " + str(len(self.ref_list)))

                # Store name for next screenshot grab
                self.name_next_grab = (convtext(name))
                # print('showNextScreenshot name_next_grab=', self.name_next_grab)

                # Restart the timer to process the next screenshot
                self.working = False
                self.updateTimer.start(1, True)

            else:
                # Error handling if screenshot grab failed
                print(("[Mosaic] retval: %d result: %s" % (retval, result)))
                try:
                    with open(grab_errorlog, "a") as f:
                        f.write("retval: %d\nresult: %s" % (retval, result))
                except BaseException:
                    pass

                # Show error message to the user
                self.session.openWithCallback(
                    self.exit,
                    MessageBox,
                    "Error while creating screenshot",
                    MessageBox.TYPE_ERROR,
                    timeout=3
                )

        except Exception as e:
            print(f'[Mosaic] showNextScreenshot Error : {str(e)}')

    def updateCountdown(self, callback=None):
        try:
            self.countdown -= 1
            self.updateCountdownLabel()
            if self.countdown == 0:
                self.countdown = config.plugins.Mosaic.countdown.value
                self.working = True
                print("[Mosaic] updateCountdown Service list:",
                      [s.toString() for s in self.ref_list])
                self.makeNextScreenshot()
            else:
                self.updateTimer.start(1000, True)
        except Exception as e:
            print(f'[Mosaic] Error in updateCountdown: {str(e)}')
            self.working = False

    def _update_info_labels(self, number):
        """Update information labels for window"""
        try:
            ref = self.window_refs[number - 1]
            info = self.serviceHandler.info(ref)
            name = info.getName(ref).replace(
                '\xc2\x86', '').replace(
                '\xc2\x87', '')
            event = self.getEventName(info)

            self[f"channel{number}"].setText(name)
            self[f"event{number}"].setText(event)
            self["count"].setText(f"Channel: {number}/{self.max_windows}")
        except Exception as e:
            print(f'[Mosaic] Error updating labels: {str(e)}')

    def toggleScreens(self):
        """Switch between 4/9 screen modes"""
        try:
            new_mode = 9 if config.plugins.Mosaic.howmanyscreens.value == 4 else 4
            config.plugins.Mosaic.howmanyscreens.value = new_mode
            config.plugins.Mosaic.howmanyscreens.save()
            self.session.openWithCallback(
                self.reload_plugin,
                MessageBox,
                _("Please restart the plugin to apply screen mode changes"),
                MessageBox.TYPE_INFO
            )
        except Exception as e:
            print(f"[Mosaic] Mode change error: {str(e)}")

    def reload_plugin(self, ret=None):
        self.close()

    def showHelp(self):
        help_text = (
            _("CH+/CH- : countdown to next screen in secs (3-30)\n") +
            _("Green   : play Mosaic\n") +
            _("Yellow  : pause Mosaic\n") +
            _("Blue    : toggle 9/4 screens\n") +
            _("1-9(4)  : switch to screen 1-9(4) and leave\n") +
            _("OK      : switch to current screen and leave\n") +
            _("Exit    : leave to previously service\n") +
            _("Help    : this help")
        )
        self.session.open(
            MessageBox,
            help_text,
            MessageBox.TYPE_INFO,
            close_on_any_key=True
        )

    def updateCountdownLabel(self):
        try:
            self["countdown"].setText(
                "%s %s / %s" %
                ("Countdown:", str(
                    self.countdown), str(
                    config.plugins.Mosaic.countdown.value)))
        except BaseException:
            pass

    def getEventName(self, info):
        try:
            event = info.getEvent()
            if event is not None:
                eventName = event.getEventName()
                if eventName is None:
                    eventName = ""
            else:
                eventName = ""
            return eventName
        except BaseException:
            return ""


Session = None
Servicelist = None
BouquetSelectorScreen = None


def trace_error():
    try:
        import traceback
        traceback.print_exc(file=stdout)
        with open(grab_errorlog, "a") as log_file:
            traceback.print_exc(file=log_file)
    except Exception as e:
        print(f'[Mosaic] Failed to log the error: {str(e)}')


def getBouquetServices(bouquet_ref):
    """Handle bouquet selection"""
    try:
        services = []
        service_handler = eServiceCenter.getInstance()
        servicelist = service_handler.list(bouquet_ref)
        if servicelist:
            service = servicelist.getNext()
            while service.valid():
                if not (
                    service.flags & (
                        eServiceReference.isDirectory | eServiceReference.isMarker)):
                    services.append(service)
                service = servicelist.getNext()
    except Exception as e:
        print(f"[Mosaic] Error parsing bouquet_ref: {str(e)}")
    return services


def closeBouquetSelectorScreen(callback=None):
    if BouquetSelectorScreen is not None:
        BouquetSelectorScreen.close()


def openMosaic(bouquet):
    if bouquet is not None:
        services = getBouquetServices(bouquet)
        if len(services):
            Session.openWithCallback(
                closeBouquetSelectorScreen, Mosaic, services)


def main(session, **kwargs):
    try:
        global Session
        Session = session
        global Servicelist

        from Screens.InfoBar import InfoBar
        InfoBarInstance = InfoBar.instance
        if InfoBarInstance is not None:
            servicelist = InfoBarInstance.servicelist
            if servicelist:
                servicelist.setMode()

        Servicelist = servicelist
        global BouquetSelectorScreen

        bouquets = Servicelist.getBouquetList()
        if bouquets is not None:
            if len(bouquets) == 1:
                openMosaic(bouquets[0][1])
            elif len(bouquets) > 1:
                BouquetSelectorScreen = Session.open(
                    BouquetSelector, bouquets, openMosaic, enableWrapAround=True)
    except Exception as e:
        print('error main', e)


def Plugins(**kwargs):
    return [
        PluginDescriptor(
            name="Mosaic 9/4 Screens",
            description="Mosaic 9/4 Screens",
            where=PluginDescriptor.WHERE_EXTENSIONSMENU,
            fnc=main
        ),
        PluginDescriptor(
            name=plugin_name,
            description=plugin_description,
            where=PluginDescriptor.WHERE_PLUGINMENU,
            icon=plugin_icon,
            fnc=main
        )
    ]
