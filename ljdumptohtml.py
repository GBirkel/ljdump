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
from datetime import *
from xml.etree import ElementTree as ET
from ljdumpsqlite import *


def write_html(filename, html_as_string):
    f = codecs.open(filename, "w", "UTF-8")
    f.write(html_as_string)


def create_template_page(journal_name, title_text):
    page = ET.Element('html',
        attrib={'class': 'csstransforms csstransitions flexbox fontface generatedcontent no-touchevents no-touch'})
    head = ET.SubElement(page, 'head')

    # So browsers will realize we're dealing with UTF-8 and interpret it correctly.
    ET.SubElement(head, 'meta',
        attrib={'charset': 'utf-8'})

    ET.SubElement(head, 'link',
        attrib={'rel': 'stylesheet', 'href': '../stylesheet.css'})
    title = ET.SubElement(head, 'title')
    title.text = title_text
    body = ET.SubElement(page, 'body',
        attrib={'class': 'page-recent two-columns column-left any-column multiple-columns two-columns-left logged-in my-journal not-subscribed has-access'})
    canvas = ET.SubElement(body, 'div', attrib={'id': 'canvas'})
    inner = ET.SubElement(canvas, 'div', attrib={'class': 'inner'})

    header = ET.SubElement(inner, 'div', attrib={'id': 'header'})
    header_inner = ET.SubElement(header, 'div', attrib={'class': 'inner'})
    header_h_title = ET.SubElement(header_inner, 'h1', attrib={'id': 'title'})
    header_h_title_span = ET.SubElement(header_h_title, 'span')
    header_h_title_span.text = journal_name
    header_h_pagetitle = ET.SubElement(header_inner, 'h2', attrib={'id': 'pagetitle'})
    header_h_pagetitle_span = ET.SubElement(header_h_pagetitle, 'span')
    header_h_pagetitle_span.text = title_text

    content = ET.SubElement(inner, 'div', attrib={'id': 'content'})
    inner_b = ET.SubElement(content, 'div', attrib={'class': 'inner'})
    primary = ET.SubElement(inner_b, 'div', attrib={'id': 'primary'})
    inner_c = ET.SubElement(primary, 'div', attrib={'class': 'inner'})
    entries = ET.SubElement(inner_c, 'div', attrib={'id': 'entries', 'class': 'hfeed'})
    inner_d = ET.SubElement(entries, 'div', attrib={'class': 'inner'})
    return (page, inner_d)


def render_comment_and_subcomments_containers(comment, comments_by_id, comment_children, icons_by_keyword, depth=1):
    # Pre-entry separator
    comment_and_thread_container = ET.Element('div',
        attrib={
            'data-comment-depth': ("%s" % depth),
            'class': ('comment-thread comment-depth-indent-desktop comment-depth-indent-mobile comment-depth-odd comment-depth-mod5-%s comment-depth-%s' % (depth, depth)),
            'style': ('--comment-depth: %s;' % (depth))})

    comment_container = ET.SubElement(comment_and_thread_container, 'div',
        attrib={
            'id': ("cmt%s" % comment['id']),
            'class': "dwexpcomment",
            'style': ('margin-left: %spx; margin-top: 5px;' % ((depth-1)*25))})
    comment_wrapper = ET.SubElement(comment_container, 'div',
        attrib={'class': "comment-wrapper comment-wrapper-odd visible full has-userpic no-subject"})

    sep_before = ET.SubElement(comment_wrapper, 'div', attrib={'class': 'separator separator-before'})
    sep_before_inner = ET.SubElement(sep_before, 'div', attrib={'class': 'inner'})

    comment_main = ET.SubElement(comment_wrapper, 'div',
        attrib={'class': 'comment',
                'id': ("comment-cmt%s" % (comment['id'])) })

    # Post-comment separator
    sep_after = ET.SubElement(comment_wrapper, 'div', attrib={'class': 'separator separator-after'})
    sep_after_inner = ET.SubElement(sep_after, 'div', attrib={'class': 'inner'})

    # Middle wrapper for comment
    comment_inner = ET.SubElement(comment_main, 'div', attrib={'class': 'inner'})

    # Comment header area
    comment_header = ET.SubElement(comment_inner, 'div', attrib={'class': 'header'})
    comment_header_inner = ET.SubElement(comment_header, 'div', attrib={'class': 'inner'})

    # Title of comment, with link to individual comment
    title = comment['subject']
    comment_title = ET.SubElement(comment_header_inner, 'h4', attrib={'class': 'comment-title'})
    comment_title.text = title

    # Datestamp
    comment_date = ET.SubElement(comment_header_inner, 'span', attrib={'class': 'datetime'})
    span_date = ET.SubElement(comment_date, 'span',
        attrib={'class': 'comment-date-text'})
    span_date.text = "Date: "
    span_date_value = ET.SubElement(comment_date, 'span')
    if comment['date_unix']:
        d = datetime.fromtimestamp(comment['date_unix'])
        span_date_value.text = html.escape(d.strftime("%b. %d, %Y %H:%M %p"))
    else:
        span_date_value.text = "(None)"

    # Another comment inner wrapper
    comment_div_contents = ET.SubElement(comment_inner, 'div', attrib={'class': 'contents'})
    comment_div_contents_inner = ET.SubElement(comment_div_contents, 'div', attrib={'class': 'inner'})

    # User icon (maybe custom, otherwise use the default)
    div_userpic = ET.SubElement(comment_div_contents_inner, 'div', attrib={'class': 'userpic'})
    # Currently no way to get userpic chosen for comment from XML-RPC.
    #userpic_k = comment['props_picture_keyword'] or '*'
    #if userpic_k in icons_by_keyword:
    #    icon = icons_by_keyword[userpic_k]
    #    img_userpic = ET.SubElement(div_userpic, 'img',
    #        attrib={'src': ("../userpics/%s" % (icon['filename']))})

    # Identify the poster (if it's not the owner)
    span_poster = ET.SubElement(comment_div_contents_inner, 'span', attrib={'class': 'poster comment-poster'})
    span_from = ET.SubElement(span_poster, 'span',
        attrib={'class': 'comment-from-text'})
    span_from.text = "From: "
    span_user = ET.SubElement(span_poster, 'span',
        attrib={'class': 'ljuser',
                'style': 'white-space: nowrap;'})
    img_user = ET.SubElement(span_user, 'img',
        attrib={'src': '../user.png',
                'style': 'vertical-align: text-bottom; border: 0; padding-right: 1px;',
                'alt': '[personal profile]'})
    if comment['user']:
        a_user = ET.SubElement(span_user, 'a',
            attrib={'href': ('https://www.dreamwidth.org/users/%s' % comment['user']),
                    'style': 'font-weight:bold;'})
        a_user.text = comment['user']
    else:
        a_user = ET.SubElement(span_user, 'span',
            attrib={'style': 'font-weight:bold;'})
        a_user.text = "(None)"

    # This is an empty div that the comment body will be placed in later.
    ET.SubElement(comment_div_contents_inner, 'div',
            attrib={'id': ("comment-content-%s-insertion-point" % comment['id'])})

    # comment footer area
    comment_footer = ET.SubElement(comment_inner, 'div', attrib={'class': 'footer'})
    comment_footer_inner = ET.SubElement(comment_footer, 'div', attrib={'class': 'inner'})

    # There are no management links here because we can't get enough data from XML-RPC to
    # reconstruct them.

    if comment['id'] in comment_children:
        for comment_id in comment_children[comment['id']]:
            next_comment = comments_by_id[comment_id]
            one_container = render_comment_and_subcomments_containers(
                                comment=next_comment,
                                comments_by_id=comments_by_id,
                                comment_children=comment_children,
                                icons_by_keyword=icons_by_keyword,
                                depth=(depth+1)
            )
            comment_and_thread_container.append(one_container)

    return comment_and_thread_container


def render_comments_section(entry, comments, comments_by_id, icons_by_keyword):
    wrapper = ET.Element('div',
        attrib={'id': ("comments-wrapper-%s" % (entry['itemid'])) })
    wrapper_inner = ET.SubElement(wrapper, 'div', attrib={'class': 'inner'})

    # Sort by ID (creation order) rather than date, since some may have been edited
    sorted_comments = sorted(comments, key=lambda x: x['id'], reverse=False)

    # Get a list of top comments only
    top_comments = []
    for comment in sorted_comments:
        if not comment['parentid']:
            top_comments.append(comment)

    # Create arrays of child comments for each comment ID.
    # Since the source list was sorted, these will be too.
    comment_children = {}
    for comment in sorted_comments:
        comment_children[comment['id']] = []
    for comment in sorted_comments:
        parent_id = comment['parentid']
        if parent_id:
            if not (parent_id in comment_children):
                comment_children[parent_id] = []
            comment_children[parent_id].append(comment['id'])

    for comment in top_comments:
        one_container = render_comment_and_subcomments_containers(
                            comment=comment,
                            comments_by_id=comments_by_id,
                            comment_children=comment_children,
                            icons_by_keyword=icons_by_keyword,
                            depth=1
        )
        wrapper_inner.append(one_container)

    return wrapper


def render_one_entry_container(journal_name, entry, comments, icons_by_keyword, moods_by_id):
    wrapper = ET.Element('div',
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

    # Entry header area
    entry_header = ET.SubElement(entry_inner, 'div', attrib={'class': 'header'})
    entry_header_inner = ET.SubElement(entry_header, 'div', attrib={'class': 'inner'})

    # Title of entry, with link to individual entry
    title = entry['subject']
    entry_title = ET.SubElement(entry_header_inner, 'h3', attrib={'class': 'entry-title'})
    entry_title_a = ET.SubElement(entry_title, 'a',
        attrib={'title': title,
                'href': ("../entries/entry-%s.html" % (entry['itemid']))})
    entry_title_a.text = title

    # Datestamp
    entry_date = ET.SubElement(entry_header_inner, 'span', attrib={'class': 'datetime'})
    d = datetime.fromtimestamp(entry['eventtime_unix'])
    entry_date.text = html.escape(d.strftime("%b. %d, %Y %H:%M %p"))

    # Another entry inner wrapper
    entry_div = ET.SubElement(entry_inner, 'div')
    entry_div_contents = ET.SubElement(entry_div, 'div', attrib={'class': 'contents'})
    entry_div_contents_inner = ET.SubElement(entry_div_contents, 'div', attrib={'class': 'inner'})

    # User icon (maybe custom, otherwise use the default)
    div_userpic = ET.SubElement(entry_div_contents_inner, 'div', attrib={'class': 'userpic'})
    userpic_k = entry['props_picture_keyword'] or '*'
    if userpic_k in icons_by_keyword:
        icon = icons_by_keyword[userpic_k]
        img_userpic = ET.SubElement(div_userpic, 'img',
            attrib={'src': ("../userpics/%s" % (icon['filename']))})

    # Identify the poster (if it's not the owner)
    span_poster = ET.SubElement(entry_div_contents_inner, 'span', attrib={'class': 'poster entry-poster'})
    span_user = ET.SubElement(span_poster, 'span',
        attrib={'class': 'ljuser',
                'style': 'white-space: nowrap;'})
    img_user = ET.SubElement(span_user, 'img',
        attrib={'src': '../user.png',
                'style': 'vertical-align: text-bottom; border: 0; padding-right: 1px;',
                'alt': '[personal profile]'})
    a_user = ET.SubElement(span_user, 'a',
        attrib={'href': ('https://www.dreamwidth.org/users/%s' % journal_name),
                'style': 'font-weight:bold;'})
    a_user.text = journal_name

    # This is an empty div that the entry body will be placed in later.
    ET.SubElement(entry_div_contents_inner, 'div',
            attrib={'class': 'entry-content',
                    'id': "entry-content-insertion-point"})

    # Entry metadata area
    if (entry['props_current_moodid'] is not None) or (entry['props_current_music'] is not None):
        entry_metadata = ET.SubElement(entry_div_contents_inner, 'div',
                attrib={'class': 'metadata bottom-metadata'})
        entry_metadata_ul = ET.SubElement(entry_metadata, 'ul')
        # Current mood
        if entry['props_current_moodid'] is not None:
            if entry['props_current_moodid'] in moods_by_id:
                mood_li = ET.SubElement(entry_metadata_ul, 'li',
                        attrib={'class': 'metadata-mood'})
                mood_label = ET.SubElement(mood_li, 'span',
                        attrib={'class': 'metadata-label metadata-label-mood'})
                mood_label.text = u"Current Mood: "
                # Alas, there is no XML-RPC support for fetching which icon set a user has.
                # There isn't even a console command for it.
                mood_name = ET.SubElement(mood_li, 'span',
                        attrib={'class': 'metadata-item metadata-item-mood'})
                mood_name.text = moods_by_id[entry['props_current_moodid']]['name']
        # Current music
        if entry['props_current_music'] is not None:
            music_li = ET.SubElement(entry_metadata_ul, 'li',
                    attrib={'class': 'metadata-music'})
            music_label = ET.SubElement(music_li, 'span',
                    attrib={'class': 'metadata-label metadata-label-music'})
            music_label.text = u"Current Music: "
            music_name = ET.SubElement(music_li, 'span',
                    attrib={'class': 'metadata-item metadata-item-music'})
            music_name.text = entry['props_current_music']

    # Entry footer area
    entry_footer = ET.SubElement(entry_inner, 'div', attrib={'class': 'footer'})
    entry_footer_inner = ET.SubElement(entry_footer, 'div', attrib={'class': 'inner'})

    # Tags (if any)
    taglist = entry['props_taglist']
    if taglist is not None:
        tags_div = ET.SubElement(entry_footer_inner, 'div', attrib={'class': 'tag'})
        tags_span = ET.SubElement(tags_div, 'span', attrib={'class': 'tag-text'})
        tags_span.text = u"Tags: "
        tags_ul = ET.SubElement(tags_div, 'ul')
        tags_split = taglist.split(', ')
        if len(tags_split) > 1:
            for i in range(0, len(tags_split)-1):
                one_tag = tags_split[i]
                tag_li = ET.SubElement(tags_ul, 'li')
                tag_a = ET.SubElement(tag_li, 'a',
                    attrib={'href': ("tags/%s.html" % one_tag),
                            'rel': 'tag'})
                tag_a.text = one_tag
                tag_a.tail = u", "
        one_tag = tags_split[-1]
        tag_li = ET.SubElement(tags_ul, 'li')
        tag_a = ET.SubElement(tag_li, 'a',
            attrib={'href': ("tags/%s.html" % one_tag),
                    'rel': 'tag'})
        tag_a.text = one_tag

    # Management links
    management_ul = ET.SubElement(entry_footer_inner, 'ul', attrib={'class': 'entry-interaction-links text-links'})
    # Permalink
    permalink_li = ET.SubElement(management_ul, 'li', attrib={'class': 'entry-permalink first-item'})
    permalink_a = ET.SubElement(permalink_li, 'a', attrib={'href': (entry['url'])})
    permalink_a.text = u"Original"
    # Comments link
    top_comments_count = 0
    for c in comments:
        if not c['parentid']:
            top_comments_count += 1
    if top_comments_count > 0:
        comments_li = ET.SubElement(management_ul, 'li', attrib={'class': 'entry-permalink first-item'})
        comments_a = ET.SubElement(comments_li, 'a', attrib={'href': ("../entries/entry-%s.html" % entry['itemid'])})
        if top_comments_count > 1:
            comments_a.text = (u"%s comments" % top_comments_count)
        else:
            comments_a.text = u"1 comment"

    return wrapper


def create_single_entry_page(journal_name, entry, comments, icons_by_keyword, moods_by_id, previous_entry=None, next_entry=None):
    page, content = create_template_page(journal_name, "%s entry %s" % (journal_name, entry['itemid']))

    # Top navigation area (e.g. "previous" and "next" links)
    topnav_div = ET.SubElement(content, 'div', attrib={'class': 'navigation topnav' })
    topnav_inner = ET.SubElement(topnav_div, 'div', attrib={'class': 'inner' })
    topnav_ul = ET.SubElement(topnav_inner, 'ul')
    if previous_entry is not None:
        topnav_li = ET.SubElement(topnav_ul, 'li', attrib={'class': 'page-back' })
        topnav_a = ET.SubElement(topnav_li, 'a', attrib={'href': ("entry-%s.html" % (previous_entry['itemid']))})
        topnav_a.text = u"Previous Entry"

    if (previous_entry is not None) and (next_entry is not None):
        topnav_li = ET.SubElement(topnav_ul, 'li', attrib={'class': 'page-separator' })
        topnav_li.text = u" | "

    if next_entry is not None:
        topnav_li = ET.SubElement(topnav_ul, 'li', attrib={'class': 'page-forward' })
        topnav_a = ET.SubElement(topnav_li, 'a', attrib={'href': ("entry-%s.html" % (next_entry['itemid']))})
        topnav_a.text = u"Next Entry"

    wrapper = render_one_entry_container(
                journal_name=journal_name,
                entry=entry,
                comments=comments,
                icons_by_keyword=icons_by_keyword,
                moods_by_id=moods_by_id
    )
    content.append(wrapper)

    # Create dictionary of comment ID to comment
    comments_by_id = {}
    for comment in comments:
        comments_by_id[comment['id']] = comment

    comments_container = render_comments_section(
                entry=entry,
                comments=comments,
                comments_by_id=comments_by_id,
                icons_by_keyword=icons_by_keyword,
    )
    content.append(comments_container)

    # Bottom navigation area (e.g. "previous" and "next" links)
    bottomnav_div = ET.SubElement(content, 'div', attrib={'class': 'navigation bottomnav' })
    bottomnav_inner = ET.SubElement(bottomnav_div, 'div', attrib={'class': 'inner' })
    bottomnav_ul = ET.SubElement(bottomnav_inner, 'ul')
    if previous_entry is not None:
        bottomnav_li = ET.SubElement(bottomnav_ul, 'li', attrib={'class': 'page-back' })
        bottomnav_a = ET.SubElement(bottomnav_li, 'a', attrib={'href': ("entry-%s.html" % (previous_entry['itemid']))})
        bottomnav_a.text = u"Previous Entry"

    if (previous_entry is not None) and (next_entry is not None):
        bottomnav_li = ET.SubElement(bottomnav_ul, 'li', attrib={'class': 'page-separator' })
        bottomnav_li.text = u" | "

    if next_entry is not None:
        bottomnav_li = ET.SubElement(bottomnav_ul, 'li', attrib={'class': 'page-forward' })
        bottomnav_a = ET.SubElement(bottomnav_li, 'a', attrib={'href': ("entry-%s.html" % (next_entry['itemid']))})
        bottomnav_a.text = u"Next Entry"

    # We're going to be weird here, because journal entries often contain weird and
    # broken HTML.  We really can't rely on parsing a journal entry into XML and then
    # embedding it as elements.  There is also no clean way to slipstream string data
    # into the XML during the rendering process (it either gets parsed as usual before
    # insertion, or run through an escaper).  So we're going to render the document as
    # text right here, and then do a text search (a split) to find the div with id
    # "entry-content-insertion-point".  Then we'll interleave the entry contents and
    # re-assemble the document.  It's hacky but it avoids the need to police the HTML
    # skills of thousands of users whose entires render fine in Dreamwidth.
    html_as_string = ET.tostring(page, encoding="utf-8", method="html").decode('utf-8')
    html_split_on_entry_body = html_as_string.split(u'<div class="entry-content" id="entry-content-insertion-point"></div>')

    text_strings = []
    entry_body = entry['event']
    entry_body = re.sub("(\r\n|\r|\n)", "<br />", entry_body)
    text_strings.append(html_split_on_entry_body[0])
    text_strings.append(u'<div class="entry-content" id="entry-content-insertion-point">')
    text_strings.append(entry_body)
    text_strings.append(u'</div>')

    remainder = html_split_on_entry_body[-1]

    # Use string substitution to insert comment bodies where they go.
    # Same hacky tactic as above, but comments can contain just as much junk HTML as
    # entries, so here we go.
    for comment in comments:
        marker = "<div id=\"comment-content-%s-insertion-point\"></div>"  % comment['id']

        comment_body = ("<div class=\"comment-content\" id=\"comment-content-%s-insertion-point\">" % comment['id']) + comment['body'] + "</div>"

        remainder = remainder.replace(marker, comment_body, 1)

    text_strings.append(remainder)
    return ''.join(text_strings)


def create_history_page(journal_name, entries, comments_grouped_by_entry, icons_by_keyword, moods_by_id, page_number, previous_page_entry_count=0, next_page_entry_count=0):
    page, content = create_template_page(journal_name, "%s entries page %s" % (journal_name, page_number))

    # Top navigation area (e.g. "previous" and "next" links)
    topnav_div = ET.SubElement(content, 'div', attrib={'class': 'navigation topnav' })
    topnav_inner = ET.SubElement(topnav_div, 'div', attrib={'class': 'inner' })
    topnav_ul = ET.SubElement(topnav_inner, 'ul')
    if previous_page_entry_count > 0:
        topnav_li = ET.SubElement(topnav_ul, 'li', attrib={'class': 'page-back' })
        topnav_a = ET.SubElement(topnav_li, 'a', attrib={'href': ("page-%s.html" % (page_number-1))})
        topnav_a.text = (u"Previous %s" % (previous_page_entry_count))

    if previous_page_entry_count > 0 and next_page_entry_count > 0:
        topnav_li = ET.SubElement(topnav_ul, 'li', attrib={'class': 'page-separator' })
        topnav_li.text = u" | "

    if next_page_entry_count > 0:
        topnav_li = ET.SubElement(topnav_ul, 'li', attrib={'class': 'page-forward' })
        topnav_a = ET.SubElement(topnav_li, 'a', attrib={'href': ("page-%s.html" % (page_number+1))})
        topnav_a.text = (u"Next %s" % (next_page_entry_count))

    for entry in entries:
        wrapper = render_one_entry_container(
                    journal_name=journal_name,
                    entry=entry,
                    comments=comments_grouped_by_entry[entry['itemid']],
                    icons_by_keyword=icons_by_keyword,
                    moods_by_id=moods_by_id
        )
        content.append(wrapper)

    # Bottom navigation area (e.g. "previous" and "next" links)
    bottomnav_div = ET.SubElement(content, 'div', attrib={'class': 'navigation bottomnav' })
    bottomnav_inner = ET.SubElement(bottomnav_div, 'div', attrib={'class': 'inner' })
    bottomnav_ul = ET.SubElement(bottomnav_inner, 'ul')
    if previous_page_entry_count > 0:
        bottomnav_li = ET.SubElement(bottomnav_ul, 'li', attrib={'class': 'page-back' })
        bottomnav_a = ET.SubElement(bottomnav_li, 'a', attrib={'href': ("page-%s.html" % (page_number-1))})
        bottomnav_a.text = (u"Previous %s" % (previous_page_entry_count))

    if previous_page_entry_count > 0 and next_page_entry_count > 0:
        bottomnav_li = ET.SubElement(bottomnav_ul, 'li', attrib={'class': 'page-separator' })
        bottomnav_li.text = u" | "

    if next_page_entry_count > 0:
        bottomnav_li = ET.SubElement(bottomnav_ul, 'li', attrib={'class': 'page-forward' })
        bottomnav_a = ET.SubElement(bottomnav_li, 'a', attrib={'href': ("page-%s.html" % (page_number+1))})
        bottomnav_a.text = (u"Next %s" % (next_page_entry_count))

    # We're going to be weird here, because journal entries often contain weird and
    # broken HTML.  We really can't rely on parsing a journal entry into XML and then
    # embedding it as elements.  There is also no clean way to slipstream string data
    # into the XML during the rendering process (it either gets parsed as usual before
    # insertion, or run through an escaper).  So we're going to render the document as
    # text right here, and then do a text search (a split) to find all the divs with id
    # "entry-content-insertion-point".  Then we'll interleave the entry contents and
    # re-assemble the document.  It's hacky but it avoids the need to police the HTML
    # skills of thousands of users whose entires render fine in Dreamwidth.
    html_as_string = ET.tostring(page, encoding="utf-8", method="html").decode('utf-8')
    html_split_on_insertion_points = html_as_string.split(u'<div class="entry-content" id="entry-content-insertion-point"></div>')

    text_strings = []
    for i in range(0, len(entries)):
        e = entries[i]
        entry_body = e['event']
        entry_body = re.sub("(\r\n|\r|\n)", "<br />", entry_body)
        text_strings.append(html_split_on_insertion_points[i])
        text_strings.append(u'<div class="entry-content" id="entry-content-insertion-point">')
        text_strings.append(entry_body)
        text_strings.append(u'</div>')
    # Add the tail end of the rendered HTML
    text_strings.append(html_split_on_insertion_points[-1])

    return ''.join(text_strings)


def ljdumptohtml(username, journal_name, verbose=True):
    if verbose:
        print("Starting conversion for: %s" % journal_name)

    conn = None
    cur = None

    # create a database connection
    conn = connect_to_local_journal_db("%s/journal.db" % journal_name, verbose)
    if not conn:
        print("Database could not be opened for journal %s" % journal_name)
        os._exit(os.EX_IOERR)
    cur = conn.cursor()

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

    # Sort all entries by UNIX timestamp, oldest to newest
    entries_by_date = sorted(all_entries, key=lambda x: x['eventtime_unix'], reverse=False)

    # Fetch all user icons and sort by keyword
    all_icons = get_all_icons(cur, verbose)
    icons_by_keyword = {}
    for icon in all_icons:
        icons_by_keyword[icon['keywords']] = icon

    # Fetch mood information and turn into a dictionary
    all_moods = get_all_moods(cur, verbose)
    moods_by_id = {}
    for mood in all_moods:
        moods_by_id[mood['id']] = mood

    #pprint.pprint(all_icons_by_keyword)

    #
    # Entry pages, one per entry.
    #

    print("Rendering %s entry pages..." % (len(entries_by_date)))

    try:
        os.mkdir("%s/entries" % (journal_name))
    except OSError as e:
        if e.errno == 17:   # Folder already exists
            pass

    for i in range(0, len(entries_by_date)):
        previous_entry = None
        if i > 0:
            previous_entry = entries_by_date[i-1]
        next_entry = None
        if i < len(entries_by_date) - 1:
            next_entry = entries_by_date[i+1]

        entry = entries_by_date[i]

        page = create_single_entry_page(
                    journal_name=journal_name,
                    entry=entry,
                    comments=comments_grouped_by_entry[entry['itemid']],
                    icons_by_keyword=icons_by_keyword,
                    moods_by_id=moods_by_id,
                    previous_entry=previous_entry,
                    next_entry=next_entry
                )
        write_html("%s/entries/entry-%s.html" % (journal_name, entry['itemid']), page)

    #
    # History pages, with 20 entries each.
    #

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

    print("Rendering %s history pages..." % (len(groups_of_twenty)))

    try:
        os.mkdir("%s/history" % (journal_name))
    except OSError as e:
        if e.errno == 17:   # Folder already exists
            pass

    for i in range(0, len(groups_of_twenty)):
        previous_count = 0
        if i > 0:
            previous_count = len(groups_of_twenty[i-1])
        next_count = 0
        if i < len(groups_of_twenty) - 1:
            next_count = len(groups_of_twenty[i+1])

        page = create_history_page(
                    journal_name=journal_name,
                    entries=groups_of_twenty[i],
                    comments_grouped_by_entry=comments_grouped_by_entry,
                    icons_by_keyword=icons_by_keyword,
                    moods_by_id=moods_by_id,
                    page_number=i+1,
                    previous_page_entry_count=previous_count,
                    next_page_entry_count=next_count
                )
        write_html("%s/history/page-%s.html" % (journal_name, i+1), page)

    print("Copying support files...")

    # Copy the default stylesheet into the journal folder
    source = "stylesheet.css"
    dest = "%s/stylesheet.css" % (journal_name)
    shutil.copyfile(source, dest)
    # Copy a generic user icon into the journal folder
    source = "user.png"
    dest = "%s/user.png" % (journal_name)
    shutil.copyfile(source, dest)

    print("Done!")


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