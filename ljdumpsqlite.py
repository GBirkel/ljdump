#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# ljdumpsqlite.py - SQLite support tools for livejournal archiver
# Version 1
#
# LICENSE
#
# This software is provided 'as-is', without any express or implied
# warranty.  In no event will the author be held liable for any damages
# arising from the use of this software.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
#
# 1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
#
# Copyright (c) 2024 Garrett Birkel and contributors

from datetime import *
import sqlite3
from sqlite3 import Error
from xml.sax import saxutils


# Subclass of tzinfo swiped mostly from dateutil
class fancytzoffset(tzinfo):
    def __init__(self, name, offset):
        self._name = name
        self._offset = timedelta(seconds=offset)
    def utcoffset(self, dt):
        return self._offset
    def dst(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return self._name
    def __eq__(self, other):
        return (isinstance(other, fancytzoffset) and self._offset == other._offset)
    def __ne__(self, other):
        return not self.__eq__(other)
    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__.__name__,
                               repr(self._name),
                               self._offset.days*86400+self._offset.seconds)
    __reduce__ = object.__reduce__


# Variant tzinfo subclass for UTC
class fancytzutc(tzinfo):
    def utcoffset(self, dt):
        return timedelta(0)
    def dst(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def __eq__(self, other):
        return (isinstance(other, fancytzutc) or
                (isinstance(other, fancytzoffset) and other._offset == timedelta(0)))
    def __ne__(self, other):
        return not self.__eq__(other)
    def __repr__(self):
        return "%s()" % self.__class__.__name__
    __reduce__ = object.__reduce__


def object_to_xml_string(accumulator, name, e):
    accumulator += ("<%s>\n" % name)
    for k in e.keys():
        if isinstance(e[k], {}.__class__):
            accumulator += object_to_xml_string(f, k, e[k])
        else:
            try:
                s = unicode(str(e[k]), "UTF-8")
            except UnicodeDecodeError:
                # fall back to Latin-1 for old entries that aren't UTF-8
                s = unicode(str(e[k]), "cp1252")
            accumulator += ("<%s>%s</%s>\n" % (k, saxutils.escape(s), k))
    accumulator += ("</%s>\n" % name)
    return accumulator


def connect_to_local_journal_db(db_file, verbose):
    """ create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :param verbose: whether we are verbose logging
    :return: Connection object or None
    """
    conn = None
    if verbose:
        print('Opening local database: %s' % db_file)
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)

    return conn


def create_tables_if_missing(conn, verbose):
    """ create needed database tables if missing
    :param conn: database connection
    :param verbose: whether we are verbose logging
    """
    if verbose:
        print('Creating tables if needed')

    conn.execute("""
        CREATE TABLE IF NOT EXISTS status (
            lastsync TEXT,
            lastmaxid INTEGER
        )""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            itemid INTEGER PRIMARY KEY NOT NULL,
            anum INTEGER,
            eventtime TEXT NOT NULL,
            eventtime_unix REAL NOT NULL,
            logtime TEXT NOT NULL,
            logtime_unix REAL NOT NULL,

            subject TEXT,
            event TEXT NOT NULL,
            url TEXT,

            props_commentalter INTEGER,
            props_current_moodid INTEGER,
            props_current_music TEXT,
            props_import_source TEXT,
            props_interface TEXT,
            props_opt_backdated INTEGER,
            props_picture_keyword TEXT,
            props_picture_mapid INTEGER,
            props_taglist TEXT,

            raw_props TEXT NOT NULL
        )""")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS entries_eventtime_unix
            ON "entries" (eventtime_unix);
        """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS entries_logtime_unix
            ON "entries" (logtime_unix);
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY NOT NULL,
            entryid INTEGER NOT NULL,
            date TEXT,
            date_unix REAL,
            parentid INTEGER,
            posterid INTEGER,
            user TEXT,
            subject TEXT,
            body TEXT,
            state TEXT
        )""")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS comments_date_unix
            ON "comments" (date_unix);
        """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS comments_entryid
            ON "comments" (entryid);
        """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS moods (
            id INTEGER PRIMARY KEY NOT NULL,
            name TEXT,
            parent INTEGER
        )
        """)

    # There is a "groups" sructure inside each tag that appears to count uses of each
    # tag in groups the user belongs to. We're not catching that here.
    # https://github.com/dreamwidth/dreamwidth/blob/18169f4a4f909527b1acc5a7eb17f90f4a56068c/cgi-bin/LJ/Protocol.pm#L3847C21-L3847C26
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            name TEXT PRIMARY KEY NOT NULL,
            display INTEGER,
            security_private INTEGER,
            security_protected INTEGER,
            security_public INTEGER,
            security_level TEXT,
            uses INTEGER
        )""")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS icons (
            keywords TEXT PRIMARY KEY NOT NULL,
            filename TEXT,
            url TEXT
        )""")


def get_status_or_defaults(cur, lastmaxid, lastsync):
    """ get values from the current status record, or create a new one if missing
    :param cur: database cursor
    :param lastmaxid: default lastmaxid value
    :param lastsync: default lastsync value
    """
    cur.execute("SELECT lastmaxid, lastsync FROM status")
    row = cur.fetchone()
    status = {"lastmaxid": lastmaxid, "lastsync": lastsync }
    if not row:
        cur.execute("INSERT INTO status (lastmaxid, lastsync) VALUES (?, ?)", (lastmaxid, lastsync))
        return (lastmaxid, lastsync)
    else:
        return (row[0], row[1])


def get_all_events(cur, verbose):
    """ get all entries in the database
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :return: An array of entry objects
    """
    if verbose:
        print('Fetching all entries from database')
    cur.execute("""
        SELECT
            itemid,
            anum,
            eventtime, eventtime_unix,
            logtime, logtime_unix,

            subject, event, url,

            props_commentalter,
            props_current_moodid,
            props_current_music,
            props_import_source,
            props_interface,
            props_opt_backdated,
            props_picture_keyword,
            props_picture_mapid,
            props_taglist,

            raw_props
        FROM entries ORDER BY itemid""")
    rows = cur.fetchall()
    entries = []
    for row in rows:
        title = (row[1] or u'')
        entry = {
            "itemid": row[0],
            "anum": row[1],
            "eventtime": row[2],
            "eventtime_unix": row[3],
            "logtime": row[4],
            "logtime_unix": row[5],

            "subject": row[6] or u'(no subject)',
            "event": row[7],
            "url": row[8],

            "props_commentalter": row[9],
            "props_current_moodid": row[10],
            "props_current_music": row[11],
            "props_import_source": row[12],
            "props_interface": row[13],
            "props_opt_backdated": row[14],
            "props_picture_keyword": row[15],
            "props_picture_mapid": row[16],
            "props_taglist": row[17],

            "raw_props": row[18],
        }
        entries.append(entry)
    return entries


def insert_or_update_event(cur, verbose, ev):
    """ insert a new entry or update any preexisting one with a matching itemid
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :param entry: entry as received from data provider
    """
    # An instance of our custom time zone class that's fixed to UTC.
    tz_utc = fancytzutc()

    eventtime = datetime.strptime(ev['eventtime'], '%Y-%m-%d %H:%M:%S')
    eventtime = eventtime.replace(tzinfo=tz_utc)
    logtime = datetime.strptime(ev['logtime'], '%Y-%m-%d %H:%M:%S')
    logtime = logtime.replace(tzinfo=tz_utc)
    # Preserve all the properties as an XML chunk in case there are
    # some we're not aware of here.
    prop_dump = object_to_xml_string('<?xml version="1.0"?>', "props", ev['props'])

    data = {
        "itemid": ev['itemid'],
        "anum": ev.get("anum", None),
        "eventtime": eventtime.isoformat(),
        "eventtime_unix": eventtime.strftime('%s'),
        "logtime": logtime.isoformat(),
        "logtime_unix": logtime.strftime('%s'),

        "subject": str(ev.get('subject', "")).decode('utf8'),
        "event": str(ev['event']).decode('utf8'),
        "url": ev.get("url", None),

        "props_commentalter": ev['props'].get("commentalter", None),
        "props_current_moodid": ev['props'].get("current_moodid", None),
        "props_current_music": ev['props'].get("current_music", None),
        "props_import_source": ev['props'].get("import_source", None),
        "props_interface": ev['props'].get("interface", None),
        "props_opt_backdated": ev['props'].get("opt_backdated", None),
        "props_picture_keyword": ev['props'].get("picture_keyword", None),
        "props_picture_mapid": ev['props'].get("picture_mapid", None),
        "props_taglist": ev['props'].get("taglist", None),

        "raw_props": prop_dump,
    }

    cur.execute("SELECT itemid FROM entries WHERE itemid = :itemid", data)
    row = cur.fetchone()
    if not row:
        if verbose:
            print('Adding new event %s at %s: %s' % (data['itemid'], data['eventtime'], data['subject']))
        cur.execute("""
            INSERT INTO entries (
                itemid,
                anum,
                eventtime, eventtime_unix,
                logtime, logtime_unix,

                subject, event, url,

                props_commentalter,
                props_current_moodid,
                props_current_music,
                props_import_source,
                props_interface,
                props_opt_backdated,
                props_picture_keyword,
                props_picture_mapid,
                props_taglist,

                raw_props
            ) VALUES (
                :itemid,
                :anum,
                :eventtime, :eventtime_unix,
                :logtime, :logtime_unix,

                :subject, :event, :url,

                :props_commentalter,
                :props_current_moodid,
                :props_current_music,
                :props_import_source,
                :props_interface,
                :props_opt_backdated,
                :props_picture_keyword,
                :props_picture_mapid,
                :props_taglist,

                :raw_props
            )""", data)
    else:
        if verbose:
            print('Updating event %s at %s: %s' % (data['itemid'], data['eventtime'], data['subject']))
        cur.execute("""
            UPDATE entries SET
                anum = :anum,
                eventtime = :eventtime,
                eventtime_unix = :eventtime_unix,
                logtime = :logtime,
                logtime_unix = :logtime_unix,

                subject = :subject,
                event = :event,
                url = :url,

                props_commentalter = :props_commentalter,
                props_current_moodid = :props_current_moodid,
                props_current_music = :props_current_music,
                props_import_source = :props_import_source,
                props_interface = :props_interface,
                props_opt_backdated = :props_opt_backdated,
                props_picture_keyword = :props_picture_keyword,
                props_picture_mapid = :props_picture_mapid,
                props_taglist = :props_taglist,

                raw_props = :raw_props

            WHERE itemid = :itemid""", data)


def get_all_comments(cur, verbose):
    """ get all comments in the database
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :return: An array of comment objects
    """
    if verbose:
        print('Fetching all comments from database')
    cur.execute("""
        SELECT
            id,
            entryid,
            date, date_unix,

            parentid,
            posterid,
            user,

            subject, body, state
        FROM comments ORDER BY id""")
    rows = cur.fetchall()
    comments = []
    for row in rows:
        title = (row[1] or u'')
        comment = {
            "id": row[0],
            "entryid": row[1],
            "date": row[2],
            "date_unix": row[3],
            "parentid": row[4],
            "posterid": row[5],
            "user": row[6],
            "subject": row[7],
            "body": row[8],
            "state": row[9],
        }
        comments.append(comment)
    return comments


def insert_or_update_comment(cur, verbose, comment):
    """ insert a new comment or update any preexisting one with a matching id
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :param comment: comment as received from data provider
    :return: True if the comment id did not already exist
    """
    # An instance of our custom time zone class that's fixed to UTC.
    tz_utc = fancytzutc()

    if comment['date'] == '':
        comment['date'] = None
        comment['date_unix'] = None
    else:
        commenttime = datetime.strptime(comment['date'], "%Y-%m-%dT%H:%M:%SZ")
        commenttime = commenttime.replace(tzinfo=tz_utc)

        comment['date'] = commenttime.isoformat()
        comment['date_unix'] = commenttime.strftime('%s')

    cur.execute("SELECT id FROM comments WHERE id = :id", comment)
    row = cur.fetchone()
    if not row:
        if verbose:
            print('Adding new comment by %s for entry %s with id %s' % (comment['user'], comment['entryid'], comment['id']))
        cur.execute("""
            INSERT INTO comments (
                id,
                entryid,
                date, date_unix,

                parentid,
                posterid,
                user,

                subject, body, state
            ) VALUES (
                :id,
                :entryid,
                :date, :date_unix,

                :parentid,
                :posterid,
                :user,

                :subject, :body, :state
            )""", comment)
        return True
    else:
        if verbose:
            print('Updating existing comment by %s for entry %s with id %s' % (comment['user'], comment['entryid'], comment['id']))
        cur.execute("""
            UPDATE comments SET
                entryid = :entryid,
                date = :date,
                date_unix = :date_unix,

                parentid = :parentid,
                posterid = :posterid,
                user = :user,

                subject = :subject,
                body = :body,
                state = :state

            WHERE id = :id""", comment)
        return False


def get_all_moods(cur, verbose):
    """ get all moods in the database
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :return: An array of mood objects
    """
    if verbose:
        print('Fetching all moods from database')
    cur.execute("SELECT id, name, parentid FROM moods")
    rows = cur.fetchall()
    moods = []
    for row in rows:
        mood = {
            "id": row[0],
            "name": row[1],
            "parentid": row[2]
        }
        moods.append(icon)
    return moods


def insert_or_update_mood(cur, verbose, data):
    """ insert a new mood or update any preexisting mood with a matching name
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :param data: mood data
    """
    cur.execute("SELECT id FROM moods WHERE id = :id", data)
    row = cur.fetchone()
    if not row:
        if verbose:
            print('Adding new mood with name: %s' % (data['name']))
        cur.execute("""
            INSERT INTO moods (
                id, name, parent
            ) VALUES (
                :id, :name, :parent
            )""", data)
    else:
        if verbose:
            print('Updating existing mood with name: %s' % (data['name']))
        cur.execute("""
            UPDATE moods SET
                name = :name,
                parent = :parent
            WHERE id = :id""", data)


def get_all_tags(cur, verbose):
    """ get all tags in the database
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :return: An array of tag objects
    """
    if verbose:
        print('Fetching all tags from database')
    cur.execute("""SELECT
        name, display,
        security_private, security_protected, security_public, security_level,
        uses FROM tags""")
    rows = cur.fetchall()
    tags = []
    for row in rows:
        tag = {
            "name": row[0],
            "display": row[1],
            "security_private": row[2],
            "security_protected": row[3],
            "security_public": row[4],
            "security_level": row[5],
            "uses": row[6]
        }
        tags.append(icon)
    return tags


def insert_or_update_tag(cur, verbose, data):
    """ insert a new tag or update any preexisting tag with a matching name
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :param data: tag data
    """
    cur.execute("SELECT name FROM tags WHERE name = :name", data)
    row = cur.fetchone()
    if not row:
        if verbose:
            print('Adding new tag with name: %s' % (data['name']))
        cur.execute("""
            INSERT INTO tags (
                name, display,
                security_private, security_protected, security_public, security_level,
                uses
            ) VALUES (
                :name, :display,
                :security_private, :security_protected, :security_public, :security_level,
                :uses
            )""", data)
    else:
        if verbose:
            print('Updating existing tag with name: %s' % (data['name']))
        cur.execute("""
            UPDATE tags SET
                display = :display,
                security_private = :security_private,
                security_protected = :security_protected,
                security_public = :security_public,
                security_level = :security_level,
                uses = :uses
            WHERE name = :name""", data)


def get_all_icons(cur, verbose):
    """ get all icons in the database
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :return: An array of icon objects
    """
    if verbose:
        print('Fetching all icons from database')
    cur.execute("SELECT keywords, filename, url FROM icons")
    rows = cur.fetchall()
    icons = []
    for row in rows:
        icon = {
            "keywords": row[0],
            "filename": row[1],
            "url": row[2]
        }
        icons.append(icon)
    return icons


def insert_or_update_icon(cur, verbose, data):
    """ insert a new icon or update any preexisting icon with matching keyeords
    :param cur: database cursor
    :param verbose: whether we are verbose logging
    :param data: icon data
    """
    cur.execute("SELECT keywords FROM icons WHERE keywords = :keywords", data)
    row = cur.fetchone()
    if not row:
        if verbose:
            print('Adding new icon with keywords: %s' % (data['keywords']))
        cur.execute("""
            INSERT INTO icons (
                keywords, filename, url
            ) VALUES (
                :keywords, :filename, :url
            )""", data)
    else:
        if verbose:
            print('Updating existing icon with keywords: %s' % (data['keywords']))
        cur.execute("""
            UPDATE icons SET
                filename = :filename,
                url = :url
            WHERE keywords = :keywords""", data)


def set_status(cur, lastmaxid, lastsync):
    """ set values in the current status record
    :param cur: database cursor
    :param lastmaxid: default lastmaxid value
    :param lastsync: default lastsync value
    """
    cur.execute("UPDATE status SET lastmaxid = ?, lastsync = ?", (lastmaxid, lastsync))


def finish_with_database(conn, cur):
    """ commit and close the cursor and database
    :param conn: database connection
    :param cur: database cursor
    """
    cur.close()
    conn.commit()
    conn.close()