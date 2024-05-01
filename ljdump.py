#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# ljdump.py - livejournal archiver
# Greg Hewgill, Garrett Birkel, et al
# Version 1.7.4
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
# Copyright (c) 2005-2010 Greg Hewgill and contributors

import argparse, codecs, os, pickle, pprint, re, shutil, sys, xml.dom.minidom
import xmlrpc.client
from getpass import getpass
import urllib
from xml.sax import saxutils
from datetime import *
import sqlite3
from sqlite3 import Error
from ljdumpsqlite import *
from ljdumptohtml import ljdumptohtml


MimeExtensions = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def getljsession(journal_server, username, password):
    """Log in with password and get session cookie."""
    d = dict(   mode="sessiongenerate",
                user=username,
                auth_method="clear",
                password=password
    )
    data = urllib.parse.urlencode(d).encode("utf-8")
    r = urllib.request.urlopen(journal_server+"/interface/flat", data=data)
    response = {}
    while True:
        name = r.readline()
        if len(name) == 0:
            break
        value = r.readline()
        response[name.decode('utf-8').strip()] = value.decode('utf-8').strip()
    r.close()
    return response['ljsession']


def gettext(e):
    if len(e) == 0:
        return ""
    return e[0].firstChild.nodeValue


def ljdump(journal_server, username, password, journal_short_name, verbose=True, stop_at_fifty=False, make_pages=False, cache_images=False, retry_images=True):

    m = re.search("(.*)/interface/xmlrpc", journal_server)
    if m:
        journal_server = m.group(1)
    if username != journal_short_name:
        authas = "&authas=%s" % journal_short_name
    else:
        authas = ""

    if verbose:
        print("Fetching journal entries for: %s" % journal_short_name)
    try:
        os.mkdir(journal_short_name)
        print("Created subdirectory: %s" % journal_short_name)
    except:
        pass

    ljsession = getljsession(journal_server, username, password)

    server = xmlrpc.client.ServerProxy(journal_server+"/interface/xmlrpc")

    def authed(params):
        """Transform API call params to include authorization."""
        return dict(auth_method='clear', username=username, password=password, **params)

    newentries = 0
    newcomments = 0
    errors = 0

    conn = None
    cur = None

    # create a database connection
    conn = connect_to_local_journal_db("%s/journal.db" % journal_short_name, verbose)
    if not conn:
        os._exit(os.EX_IOERR)
    create_tables_if_missing(conn, verbose)
    cur = conn.cursor()

    (lastmaxid, lastsync) = get_status_or_defaults(cur, 0, "")

    #
    # Entries (events)
    #

    origlastsync = lastsync

    # The following code doesn't work because the server rejects our repeated calls.
    # https://www.livejournal.com/doc/server/ljp.csp.xml-rpc.getevents.html
    # contains the statement "You should use the syncitems selecttype in
    # conjuntions [sic] with the syncitems protocol mode", but provides
    # no other explanation about how these two function calls should
    # interact. Therefore we just do the above slow one-at-a-time method.
    #
    #    r = server.LJ.XMLRPC.getevents(authed({
    #        'ver': 1,
    #        'selecttype': "syncitems",
    #        'lastsync': lastsync,
    #    }))

    # For testing purposes:
    #r = server.LJ.XMLRPC.getdaycounts(authed({
    #    'ver': 1,
    #}))
    #pprint.pprint(r)
    #os._exit(os.EX_OK)

    r = server.LJ.XMLRPC.syncitems(authed({
        'ver': 1,
        'lastsync': lastsync, # this one is not helpful when you want update existing stuff
        'usejournal': journal_short_name,
    }))

    if verbose:
        print("Sync items to handle: %s" % (len(r['syncitems'])))

    for item in r['syncitems']:
        if item['item'][0] == 'L':
            if verbose:
                print("Fetching journal entry %s (%s)" % (item['item'], item['action']))
            try:
                e = server.LJ.XMLRPC.getevents(authed({
                    'ver': 1,
                    'selecttype': "one",
                    'itemid': item['item'][2:],
                    'usejournal': journal_short_name,
                }))
                if e['events']:
                    ev = e['events'][0]
                    newentries += 1

                    # Process the event

                    # Wanna do a bulk replace of something in your entire journal? This is now.
                    #ev['event'] = re.sub('http://(edu.|staff.|)mmcs.sfedu.ru/~ulysses',
                    #                     'https://a-pelenitsyn.github.io/Files',
                    #                     str(ev['event']))
                    # Write modified event to server
                    #d = datetime.strptime(ev['eventtime'], '%Y-%m-%d %H:%M:%S')
                    #ev1 = dict(lineendings="pc", year=d.year, mon=d.month, day=d.day,
                    #          hour=d.hour, min=d.minute, **ev)
                    #r1 = server.LJ.XMLRPC.editevent(authed(ev1))

                    insert_or_update_event(cur, verbose, ev)

                    if stop_at_fifty and newentries > 49:
                        break

                else:
                    print("Unexpected empty item: %s" % item['item'])
                    errors += 1
            except xmlrpc.client.Fault as x:
                print("Error getting item: %s" % item['item'])
                pprint.pprint(x)
                errors += 1

        lastsync = item['time']
    
    if stop_at_fifty:
        set_status(cur, lastmaxid, lastsync)
        finish_with_database(conn, cur)
        os._exit(os.EX_OK)
    
    #
    # Comments
    #

    if verbose:
        print("Fetching journal comments for: %s" % journal_short_name)

    try:
        f = open("%s/comment.meta" % journal_short_name)
        metacache = pickle.load(f)
        f.close()
    except:
        metacache = {}

    maxid = lastmaxid
    while True:
        try:
            try:
                r = urllib.request.urlopen(
                        urllib.request.Request(
                            journal_server+"/export_comments.bml?get=comment_meta&startid=%d%s" % (maxid+1, authas),
                            headers = {'Cookie': "ljsession="+ljsession}
                       )
                    )
                meta = xml.dom.minidom.parse(r)
            except Exception as x:
                print("*** Error fetching comment meta, possibly not community maintainer?")
                print("***", x)
                break
        finally:
            try:
                r.close()
            except AttributeError: # r is sometimes a dict for unknown reasons
                pass

        for c in meta.getElementsByTagName("comment"):
            id = int(c.getAttribute("id"))
            metacache[id] = {
                'posterid': c.getAttribute("posterid"),
                'state': c.getAttribute("state"),
            }
            if id > maxid:
                maxid = id
        for u in meta.getElementsByTagName("usermap"):
            insert_or_update_user_in_map(cur, verbose, u.getAttribute("id"), u.getAttribute("user"))
        if maxid >= int(meta.getElementsByTagName("maxid")[0].firstChild.nodeValue):
            break

    usermap = get_users_map(cur, verbose)

    newmaxid = maxid
    maxid = lastmaxid

    # Make a reduced array of comment ids, containing only the ids
    # between the id of the comment we fetched in the last session,
    # and the highest comment id in the set of new comments.
    new_comment_ids = []
    for commentid in metacache.keys():
        if commentid > maxid and commentid <= newmaxid:
            new_comment_ids.append(commentid)
    # Now put them in order from lowest to highest, because we're going to
    # fetch comments in pages and skip the ones already fetched, and the
    # pages will be in ascending order as well.
    sorted_new_comment_ids = sorted(new_comment_ids, key=lambda x: x, reverse=False)
    # There can be gaps in the id sequence larger than the size of a page,
    # which means fetching using a startid of "last id in the previous page" + 1
    # can potentially return a blank page and make it look like the fetch is complete.
    # Drawing from a sorted array of known-good ids (and skipping the ones we
    # already fetched) avoids this problem.
    comments_already_fetched = {}

    for commentid in sorted_new_comment_ids:
        if commentid in comments_already_fetched:
            continue
        try:
            if verbose:
                print('Fetching comment bodies starting at %s' % (commentid))
            try:
                r = urllib.request.urlopen(
                    urllib.request.Request(
                        journal_server+"/export_comments.bml?get=comment_body&startid=%d%s" % (commentid, authas),
                        headers = {'Cookie': "ljsession="+ljsession}
                    )
                )
                meta = xml.dom.minidom.parse(r)
            except Exception as x:
                print("*** Error fetching comment body, possibly not community maintainer?")
                print("***", x)
                break
        finally:
            r.close()
        for c in meta.getElementsByTagName("comment"):
            id = int(c.getAttribute("id"))
            if id in comments_already_fetched:
                continue
            jitemid = c.getAttribute("jitemid")

            db_comment = {
                'id': id,
                'entryid': int(jitemid),
                'date': gettext(c.getElementsByTagName("date")),
                'parentid': c.getAttribute("parentid"),
                'posterid': c.getAttribute("posterid"),
                'user': None,
                'subject': gettext(c.getElementsByTagName("subject")),
                'body': gettext(c.getElementsByTagName("body")),
                'state': metacache[id]['state']
            }
            try:
                if int(c.getAttribute("posterid")) in usermap:
                    db_comment["user"] = usermap[int(c.getAttribute("posterid"))]
            except ValueError:
                pass

            was_new = insert_or_update_comment(cur, verbose, db_comment)
            if was_new:
                newcomments += 1

            comments_already_fetched[id] = True

            if id > maxid:
                maxid = id

    #
    # Mood information
    #

    r = server.LJ.XMLRPC.login(authed({
        'ver': 1,
        'getmoods': 1,
    }))

    for t in r['moods']:
        insert_or_update_mood(cur, verbose,
            {   'id': t['id'],
                'name': t['name'],
                'parent': t['parent']})

    #
    # Tag information
    #

    r = server.LJ.XMLRPC.getusertags(authed({
        'ver': 1,
    }))

    for t in r['tags']:
        insert_or_update_tag(cur, verbose,
            {   'name': t['name'],
                'display': t['display'],
                'security_private': t['security']['private'],
                'security_protected': t['security']['protected'],
                'security_public': t['security']['public'],
                'security_level': t['display'],
                'uses': t['uses']})

    #
    # Userpics and user general info
    #

    r = server.LJ.XMLRPC.login(authed({
        'ver': 1,
        'getpickws': 1,
        'getpickwurls': 1,
    }))

    userpics = dict(zip(map(str, r['pickws']), r['pickwurls']))
    if r['defaultpicurl']:
        userpics['*'] = r['defaultpicurl']

    insert_or_update_user_info(cur, verbose,
        {   'journal_short_name': journal_short_name,
            'defaultpicurl': r['defaultpicurl'],
            'fullname': r['fullname'],
            'userid': r['userid']
        })

    if username == journal_short_name:
        try:
            os.mkdir("%s/userpics" % (journal_short_name))
        except OSError as e:
            if e.errno == 17:   # Folder already exists
                pass
        if verbose:
            print("Fetching userpics for: %s" % journal_short_name)

        for p in userpics:
            pic = urllib.request.urlopen(userpics[p])
            ext = MimeExtensions.get(pic.info()["Content-Type"], "")
            picfn = re.sub(r'[*?\\/:<> "|]', "_", p)
            try:
                picfn = codecs.utf_8_decode(picfn)[0]
                picf = open("%s/userpics/%s%s" % (journal_short_name, picfn, ext), "wb")
            except:
                # for installations where the above utf_8_decode doesn't work
                picfn = "".join([ord(x) < 128 and x or "_" for x in picfn])
                picf = open("%s/userpics/%s%s" % (journal_short_name, picfn, ext), "wb")
            shutil.copyfileobj(pic, picf)
            pic.close()
            picf.close()
            insert_or_update_icon(cur, verbose,
                {'keywords': p,
                    'filename': (picfn+ext),
                    'url': userpics[p]})

    lastmaxid = maxid

    set_status(cur, lastmaxid, lastsync)

    if verbose or (newentries > 0 or newcomments > 0):
        if origlastsync:
            print("%d new entries, %d new comments (since %s)" % (newentries, newcomments, origlastsync))
        else:
            print("%d new entries, %d new comments" % (newentries, newcomments))
    if errors > 0:
        print("%d errors" % errors)

    finish_with_database(conn, cur)

    if make_pages:
        ljdumptohtml(
            username=username,
            journal_short_name=journal_short_name,
            verbose=verbose,
            cache_images=cache_images,
            retry_images=retry_images
        )

if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Livejournal archive utility")
    args.add_argument("--quiet", "-q", action='store_false', dest='verbose',
                      help="reduce log output")
    args.add_argument("--no_html", "-n", action='store_false', dest='make_pages',
                      help="don't process the journal data into HTML files.")
    args.add_argument("--fifty", "-f", action='store_true', dest='fifty',
                      help="stop after synchronizing 50 entries, and do not fetch anything else")
    args.add_argument("--cache_images", "-i", action='store_true', dest='cache_images',
                      help="build a cache of images referenced in entries")
    args.add_argument("--dont_retry_images", "-d", action='store_false', dest='retry_images',
                      help="don't retry images that failed to cache once already")
    args = args.parse_args()
    if os.access("ljdump.config", os.F_OK):
        config = xml.dom.minidom.parse("ljdump.config")
        journal_server = config.documentElement.getElementsByTagName("server")[0].childNodes[0].data
        username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
        password_els = config.documentElement.getElementsByTagName("password")
        if len(password_els) > 0:
            password = password_els[0].childNodes[0].data
        else:
            password = getpass("Password: ")
        journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
        if not journals:
            journals = [username]
    else:
        print("ljdump - livejournal archiver")
        print
        default_server = "https://livejournal.com"
        journal_server = input("Alternative server to use (e.g. 'https://www.dreamwidth.org'), or hit return for '%s': " % default_server) or default_server
        print
        print("Enter your Livejournal (or Dreamwidth, etc) username and password.")
        print
        username = input("Username: ")
        password = getpass("Password: ")
        print
        print("You may back up either your own journal, or a community.")
        print("If you are a community maintainer, you can back up both entries and comments.")
        print("If you are not a maintainer, you can back up only entries.")
        print
        journal = input("Journal to back up (or hit return to back up '%s'): " % username)
        print
        if journal:
            journals = [journal]
        else:
            journals = [username]

    for journal in journals:
        ljdump(
            journal_server=journal_server,
            username=username,
            password=password,
            journal_short_name=journal,
            verbose=args.verbose,
            stop_at_fifty=args.fifty,
            make_pages=args.make_pages,
            cache_images=args.cache_images,
            retry_images=args.retry_images
        )
# vim:ts=4 et:	
