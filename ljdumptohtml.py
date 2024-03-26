#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# ljdumptohtml.py - convert sqlite livejournal archive to html pages 
# Garrett Birkel et al
# Version 0.5(alpha)
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


import sys, os, codecs, pprint, argparse, shutil, xml.dom.minidom
import html
import re
from xml.etree import ElementTree as ET
from ljdumpsqlite import *


def write_html(filename, html_as_string):
    f = codecs.open(filename, "w", "UTF-8")
    f.write(html_as_string)


def create_template_page(title_text):
    page = ET.Element('html',
        attrib={'class': 'csstransforms csstransitions flexbox fontface generatedcontent no-touchevents no-touch'})
    head = ET.SubElement(page, 'head')
    ET.SubElement(head, 'link',
        attrib={'rel': 'stylesheet', 'href': 'stylesheet.css'})
    title = ET.SubElement(head, 'title')
    title.text = title_text
    body = ET.SubElement(page, 'body',
        attrib={'class': 'page-recent two-columns column-left any-column multiple-columns two-columns-left logged-in my-journal not-subscribed has-access'})
    canvas = ET.SubElement(body, 'div', attrib={'id': 'canvas'})
    inner = ET.SubElement(canvas, 'div', attrib={'class': 'inner'})
    content = ET.SubElement(inner, 'div', attrib={'id': 'content'})
    inner_b = ET.SubElement(content, 'div', attrib={'class': 'inner'})
    primary = ET.SubElement(inner_b, 'div', attrib={'id': 'primary'})
    inner_c = ET.SubElement(primary, 'div', attrib={'class': 'inner'})
    entries = ET.SubElement(inner_c, 'div', attrib={'id': 'entries', 'class': 'hfeed'})
    inner_d = ET.SubElement(entries, 'div', attrib={'class': 'inner'})
    return (page, inner_d)


def create_history_page(Journal, group, page_number, comments_grouped_by_entry, all_icons_by_keyword):
    page, content = create_template_page("%s entries page %s" % (Journal, page_number))
    for entry in group:
        wrapper = ET.SubElement(content, 'div',
            attrib={'class': 'entry-wrapper entry-wrapper-odd security-public restrictions-none journal-type-P has-userpic has-subject',
                    'id': ("entry-wrapper-%s" % (entry['itemid'])) })

        # Pre-entry separator
        sep_before = ET.SubElement(wrapper, 'div', attrib={'class': 'separator separator-before'})
        sep_before_inner = ET.SubElement(sep_before, 'div', attrib={'class': 'inner'})

        entry_div = ET.SubElement(wrapper, 'div',
            attrib={'class': 'entry',
                    'id': ("entry-%s" % (entry['itemid'])) })

        # Post-entry separator
        sep_after = ET.SubElement(wrapper, 'div', attrib={'class': 'separator separator-after'})
        sep_after_inner = ET.SubElement(sep_after, 'div', attrib={'class': 'inner'})

        # Middle wrapper for entry
        entry_inner = ET.SubElement(entry_div, 'div', attrib={'class': 'inner'})
        entry_header = ET.SubElement(entry_inner, 'div', attrib={'class': 'header'})
        entry_header_inner = ET.SubElement(entry_header, 'div', attrib={'class': 'inner'})

        # Title of entry, with link to individual entry
        entry_title = ET.SubElement(entry_header_inner, 'h3', attrib={'class': 'entry-title'})
        entry_title_a = ET.SubElement(entry_title, 'a',
            attrib={'title': html.escape(entry['subject']),
                    'href': ("entries/entry-%s.html" % (entry['itemid']))})
        entry_title_a.text = entry['subject']

        # Datestamp
        entry_date = ET.SubElement(entry_header_inner, 'span', attrib={'class': 'datetime'})
        entry_date.text = html.escape(entry['logtime'])

        # Another entry inner wrapper
        entry_div = ET.SubElement(entry_inner, 'div')
        entry_div_contents = ET.SubElement(entry_div, 'div', attrib={'class': 'contents'})
        entry_div_contents_inner = ET.SubElement(entry_div_contents, 'div', attrib={'class': 'inner'})

        # User icon (maybe custom, otherwise use the default)
        div_userpic = ET.SubElement(entry_div_contents_inner, 'div', attrib={'class': 'userpic'})
        userpic_k = entry['props_picture_keyword'] or '*'
        if userpic_k in all_icons_by_keyword:
            icon = all_icons_by_keyword[userpic_k]
            img_userpic = ET.SubElement(div_userpic, 'img',
                attrib={'src': ("userpics/%s" % (icon['filename']))})

        # Identify the poster (if it's not the owner)
        span_poster = ET.SubElement(entry_div_contents_inner, 'span', attrib={'class': 'poster entry-poster empty'})

        # This is an empty div that the entry body will be placed in later.
        ET.SubElement(entry_div_contents_inner, 'div',
                attrib={'class': 'entry-content',
                        'id': "entry-content-insertion-point"})

        comment_count = comments_grouped_by_entry[entry['itemid']]


    # We're going to be weird here, because journal entries often contain weird and
    # broken HTML.  We really can't rely on parsing a journal entry into XML and then
    # embedding it as elements.  There is also no clean way to slipstream string data
    # into the XML during the rendering process (it either gets parsed as usual before
    # insertion, or run through an escaper).  So we're going to render the document as
    # text right here, and then do a text search (a split) to find all the divs with id
    # "entry-content-insertion-point".  Then we'll interleave the entry contents and
    # re-assemble the document.  It's hacky but it avoids the need to police the HTML
    # skills of thousands of users whose entires render fine in Dreamwidth.
    html_as_string = ET.tostring(page, encoding='utf8', method='html')
    html_split_on_insertion_points = html_as_string.split('<div class="entry-content" id="entry-content-insertion-point"></div>')

    text_strings = []
    for i in range(0, len(group)):
        e = group[i]
        entry_body = e['event']
        entry_body = re.sub("\n", "<br />\n", entry_body)
        text_strings.append(html_split_on_insertion_points[i])
        text_strings.append(u'<div class="entry-content" id="entry-content-insertion-point">')
        text_strings.append(entry_body)
        text_strings.append(u'</div>')
    # Add the tail end of the rendered HTML
    text_strings.append(html_split_on_insertion_points[-1])

    return u''.join(text_strings)


def ljdumptohtml(Username, Journal, verbose=True):
    if verbose:
        print("Starting conversion for: %s" % Journal)

    conn = None
    cur = None

    # create a database connection
    conn = connect_to_local_journal_db("%s/journal.db" % Journal, verbose)
    if not conn:
        print("Database could not be opened for journal %s" % Journal)
        os._exit(os.EX_IOERR)
    cur = conn.cursor()

    styles_source = "stylesheet.css"
    styles_copy = "%s/stylesheet.css" % (Journal)
    shutil.copyfile(styles_source, styles_copy)

    all_entries = get_all_events(cur, verbose)
    all_comments = get_all_comments(cur, verbose)

    # Create arrays of comments by entry ID
    comments_grouped_by_entry = {}
    for entry in all_entries:
        e_id = entry['itemid']
        # Make sure every entry has an array even if it has 0 comments
        comments_grouped_by_entry[e_id] = []
    for comment in all_comments:
        e_id = comment['entryid']
        if not (e_id in comments_grouped_by_entry):
            comments_grouped_by_entry[e_id] = []
        comments_grouped_by_entry[e_id].append(comment)

    # Create arrays of child comments for each comment ID
    comment_children = {}
    for comment in all_comments:
        id = comment['id']
        comment_children[id] = []
    for comment in all_comments:
        id = comment['id']
        parent_id = comment['parentid']
        if parent_id:
            if not (parent_id in comment_children):
                comment_children[parent_id] = []
            comment_children[parent_id].append(id)

    # Sort all entries by UNIX timestamp, oldest to newest
    entries_by_date = sorted(all_entries, key=lambda x: x['logtime_unix'], reverse=False)

    # Create groups of 20 entries for the history pages
    groups_of_twenty = []
    current_group = []
    for entry in entries_by_date:
        current_group.append(entry)
        if len(current_group) > 19:
            groups_of_twenty.append(current_group)
            current_group = []
    if len(current_group) > 0:
        groups_of_twenty.append(current_group)

    # Fetch all user icons and sort by keyword
    all_icons = get_all_icons(cur, verbose)
    all_icons_by_keyword = {}
    for icon in all_icons:
        all_icons_by_keyword[icon['keywords']] = icon

    #pprint.pprint(all_icons_by_keyword)

    page = create_history_page(Journal, groups_of_twenty[0], 1, comments_grouped_by_entry, all_icons_by_keyword)
    write_html("%s/page%s.html" % (Journal, 1), page)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Livejournal archive to html utility")
    args.add_argument("--quiet", "-q", action='store_false', dest='verbose',
                      help="reduce log output")
    args = args.parse_args()
    if os.access("ljdump.config", os.F_OK):
        config = xml.dom.minidom.parse("ljdump.config")
        username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
        journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
        if not journals:
            journals = [username]
    else:
        print("ljdumptohtml - livejournal (or Dreamwidth, etc) archive to html utility")
        print
        default_server = "https://livejournal.com"
        server = raw_input("Alternative server to use (e.g. 'https://www.dreamwidth.org'), or hit return for '%s': " % default_server) or default_server
        print
        print("Enter your Livejournal (or Dreamwidth, etc) username.")
        print
        username = raw_input("Username: ")
        print
        journal = raw_input("Journal to render (or hit return to render '%s'): " % username)
        print
        if journal:
            journals = [journal]
        else:
            journals = [username]

    for journal in journals:
        ljdumptohtml(username, journal, args.verbose)