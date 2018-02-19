# -*- coding: utf-8 -*-
# main.py - main module, starts game and main loop
# This file is part of brutalmaze
#
# brutalmaze is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# brutalmaze is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with brutalmaze.  If not, see <http://www.gnu.org/licenses/>.
#
# Copyright (C) 2017 Nguyễn Gia Phong

__version__ = '0.5.3'

import re
from argparse import ArgumentParser, FileType, RawTextHelpFormatter
from collections import deque
try:                    # Python 3
    from configparser import ConfigParser
except ImportError:     # Python 2
    from ConfigParser import ConfigParser
from os.path import join, pathsep
from sys import stdout


import pygame
from pygame import DOUBLEBUF, KEYDOWN, OPENGL, QUIT, RESIZABLE, VIDEORESIZE
from pygame.time import Clock, get_ticks
from appdirs import AppDirs

from .constants import SETTINGS, ICON, MUSIC, HERO_SPEED
from .maze import Maze
from .misc import sign


class ConfigReader:
    """Object reading and processing INI configuration file for
    Brutal Maze.
    """
    CONTROL_ALIASES = (('New game', 'new'), ('Toggle pause', 'pause'),
                       ('Toggle mute', 'mute'),
                       ('Move left', 'left'), ('Move right', 'right'),
                       ('Move up', 'up'), ('Move down', 'down'),
                       ('Long-range attack', 'shot'),
                       ('Close-range attack', 'slash'))
    WEIRD_MOUSE_ERR = '{}: Mouse is not a suitable control'
    INVALID_CONTROL_ERR = '{}: {} is not recognized as a valid control key'

    def __init__(self, filenames):
        self.config = ConfigParser()
        self.config.read(SETTINGS)  # default configuration
        self.config.read(filenames)

    def parse_output(self):
        """Parse graphics and sound configurations."""
        self.size = (self.config.getint('Graphics', 'Screen width'),
                     self.config.getint('Graphics', 'Screen height'))
        self.opengl = self.config.getboolean('Graphics', 'OpenGL')
        self.max_fps = self.config.getint('Graphics', 'Maximum FPS')
        self.muted = self.config.getboolean('Sound', 'Muted')
        self.musicvol = self.config.getfloat('Sound', 'Music volume')

    def parse_control(self):
        """Parse control configurations."""
        self.key, self.mouse = {}, {}
        for cmd, alias in self.CONTROL_ALIASES:
            i = self.config.get('Control', cmd)
            if re.match('mouse[1-3]$', i.lower()):
                if alias not in ('shot', 'slash'):
                    raise ValueError(self.WEIRD_MOUSE_ERR.format(cmd))
                self.mouse[alias] = int(i[-1]) - 1
                continue
            if len(i) == 1:
                self.key[alias] = ord(i.lower())
                continue
            try:
                self.key[alias] = getattr(pygame, 'K_{}'.format(i.upper()))
            except AttributeError:
                raise ValueError(self.INVALID_CONTROL_ERR.format(cmd, i))

    def read_args(self, arguments):
        """Read and parse a ArgumentParser.Namespace."""
        for option in 'size', 'opengl', 'max_fps', 'muted', 'musicvol':
            value = getattr(arguments, option)
            if value is not None: setattr(self, option, value)


class Game:
    """Object handling main loop and IO."""
    def __init__(self, size, scrtype, max_fps, muted, musicvol, key, mouse):
        pygame.mixer.pre_init(frequency=44100)
        pygame.init()
        if muted:
            pygame.mixer.quit()
        else:
            pygame.mixer.music.load(MUSIC)
            pygame.mixer.music.set_volume(musicvol)
            pygame.mixer.music.play(-1)
        pygame.display.set_icon(ICON)
        pygame.fastevent.init()
        # self.fps is a float to make sure floordiv won't be used in Python 2
        self.max_fps, self.fps = max_fps, float(max_fps)
        self.musicvol = musicvol
        self.key, self.mouse = key, mouse
        self.maze = Maze(max_fps, size, scrtype)
        self.hero = self.maze.hero
        self.clock, self.paused = Clock(), False

    def __enter__(self): return self

    def move(self, x, y):
        """Command the hero to move faster in the given direction."""
        stunned = pygame.time.get_ticks() < self.maze.next_move
        velocity = self.maze.distance * HERO_SPEED / self.fps
        accel = velocity * HERO_SPEED / self.fps

        if stunned or not x:
            self.maze.vx -= sign(self.maze.vx) * accel
            if abs(self.maze.vx) < accel * 2: self.maze.vx = 0.0
        elif x * self.maze.vx < 0:
            self.maze.vx += x * 2 * accel
        else:
            self.maze.vx += x * accel
            if abs(self.maze.vx) > velocity: self.maze.vx = x * velocity

        if stunned or not y:
            self.maze.vy -= sign(self.maze.vy) * accel
            if abs(self.maze.vy) < accel * 2: self.maze.vy = 0.0
        elif y * self.maze.vy < 0:
            self.maze.vy += y * 2 * accel
        else:
            self.maze.vy += y * accel
            if abs(self.maze.vy) > velocity: self.maze.vy = y * velocity

    def loop(self):
        """Start and handle main loop."""
        events = pygame.fastevent.get()
        for event in events:
            if event.type == QUIT:
                return False
            elif event.type == VIDEORESIZE:
                self.maze.resize((event.w, event.h))
            elif event.type == KEYDOWN:
                if event.key == self.key['new']:
                    self.maze.__init__(self.fps)
                elif event.key == self.key['pause'] and not self.hero.dead:
                    self.paused ^= True
                elif event.key == self.key['mute']:
                    if pygame.mixer.get_init() is None:
                        pygame.mixer.init(frequency=44100)
                        pygame.mixer.music.load(MUSIC)
                        pygame.mixer.music.set_volume(self.musicvol)
                        pygame.mixer.music.play(-1)
                    else:
                        pygame.mixer.quit()

        if not self.hero.dead:
            keys = pygame.key.get_pressed()
            self.move(keys[self.key['left']] - keys[self.key['right']],
                      keys[self.key['up']] - keys[self.key['down']])
            buttons = pygame.mouse.get_pressed()
            try:
                self.hero.firing = keys[self.key['shot']]
            except KeyError:
                self.hero.firing = buttons[self.mouse['shot']]
            try:
                self.hero.slashing = keys[self.key['slash']]
            except KeyError:
                self.hero.slashing = buttons[self.mouse['slash']]

        # Compare current FPS with the average of the last 10 frames
        new_fps = self.clock.get_fps()
        if new_fps < self.fps:
            self.fps -= 1
        elif self.fps < self.max_fps and not self.paused:
            self.fps += 5
        if not self.paused: self.maze.update(self.fps)
        self.clock.tick(self.fps)
        return True

    def __exit__(self, exc_type, exc_value, traceback): pygame.quit()


def main():
    """Start game and main loop."""
    # Read configuration file
    dirs = AppDirs(appname='brutalmaze', appauthor=False, multipath=True)
    parents = dirs.site_config_dir.split(pathsep)
    parents.append(dirs.user_config_dir)
    filenames = [join(parent, 'settings.ini') for parent in parents]
    config = ConfigReader(filenames)
    config.parse_output()

    # Parse command-line arguments
    parser = ArgumentParser(formatter_class=RawTextHelpFormatter)
    parser.add_argument('-v', '--version', action='version',
                        version='Brutal Maze {}'.format(__version__))
    parser.add_argument(
        '--write-config', nargs='?', const=stdout, type=FileType('w'),
        metavar='PATH', dest='defaultcfg',
        help='write default config and exit, if PATH not specified use stdout')
    parser.add_argument(
        '-c', '--config', metavar='PATH',
        help='location of the configuration file (fallback: {})'.format(
            pathsep.join(filenames)))
    parser.add_argument(
        '-s', '--size', type=int, nargs=2, metavar=('X', 'Y'),
        help='the desired screen size (fallback: {}x{})'.format(*config.size))
    parser.add_argument(
        '--opengl', action='store_true', default=None,
        help='enable OpenGL (fallback: {})'.format(config.opengl))
    parser.add_argument('--no-opengl', action='store_false', dest='opengl',
                        help='disable OpenGL')
    parser.add_argument(
        '-f', '--max-fps', type=int, metavar='FPS',
        help='the desired maximum FPS (fallback: {})'.format(config.max_fps))
    parser.add_argument(
        '--mute', '-m', action='store_true', default=None,
        help='mute all sounds (fallback: {})'.format(config.muted))
    parser.add_argument('--unmute', action='store_false', dest='muted',
                        help='unmute sound')
    parser.add_argument(
        '--music-volume', type=float, metavar='VOL', dest='musicvol',
        help='between 0.0 and 1.0 (fallback: {})'.format(config.musicvol))
    args = parser.parse_args()
    if args.defaultcfg is not None:
        with open(SETTINGS) as settings: args.defaultcfg.write(settings.read())
        args.defaultcfg.close()
        exit()

    # Manipulate config
    if args.config: config.config.read(args.config)
    config.read_args(args)
    config.parse_output()
    config.parse_control()

    # Main loop
    scrtype = (config.opengl and DOUBLEBUF|OPENGL) | RESIZABLE
    with Game(config.size, scrtype, config.max_fps, config.muted,
              config.musicvol, config.key, config.mouse) as game:
        while game.loop(): pass
