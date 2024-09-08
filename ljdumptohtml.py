#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# ljdumptohtml.py - convert sqlite livejournal archive to html pages 
# Garrett Birkel et al
# Version 1.7.8
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
from getpass import getpass
import urllib
import html
import re
import calendar
from datetime import *
from xml.etree import ElementTree as ET
from ljdumpsqlite import *


MimeExtensions = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def write_html(filename, html_as_string):
    f = codecs.open(filename, "w", "UTF-8")
    f.write(html_as_string)


def create_template_page(journal_short_name, title_text):
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
    header_h_title_span.text = journal_short_name
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
        d = datetime.utcfromtimestamp(comment['date_unix'])
        # If anybody has a way to get rid of the leading zero that works in MacOS and Windows 11, let me know.
        dh = int(f'{d:%I}')
        span_date_value.text = html.escape(f'{d:%b}. {d.day}, {d:%Y} {dh}:{d:%M} {d:%p}')
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


def render_one_entry_container(journal_short_name, entry, comments_count, icons_by_keyword, moods_by_id):
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
    d = datetime.utcfromtimestamp(entry['eventtime_unix'])
    # If anybody has a way to get rid of the leading zero that works in MacOS and Windows 11, let me know.
    dh = int(f'{d:%I}')
    entry_date.text = html.escape(f'{d:%b}. {d.day}, {d:%Y} {dh}:{d:%M} {d:%p}')

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
        attrib={'href': ('https://www.dreamwidth.org/users/%s' % journal_short_name),
                'style': 'font-weight:bold;'})
    a_user.text = journal_short_name

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
                    attrib={'href': ("../index.html#%s" % one_tag),
                            'rel': 'tag'})
                tag_a.text = one_tag
                tag_a.tail = u", "
        one_tag = tags_split[-1]
        tag_li = ET.SubElement(tags_ul, 'li')
        tag_a = ET.SubElement(tag_li, 'a',
            attrib={'href': ("../index.html#%s" % one_tag),
                    'rel': 'tag'})
        tag_a.text = one_tag

    # Management links
    management_ul = ET.SubElement(entry_footer_inner, 'ul', attrib={'class': 'entry-interaction-links text-links'})
    # Permalink
    permalink_li = ET.SubElement(management_ul, 'li', attrib={'class': 'entry-permalink first-item'})
    permalink_a = ET.SubElement(permalink_li, 'a', attrib={'href': (entry['url'])})
    permalink_a.text = u"Original"
    # Comments link
    if comments_count > 0:
        comments_li = ET.SubElement(management_ul, 'li', attrib={'class': 'entry-permalink first-item'})
        comments_a = ET.SubElement(comments_li, 'a', attrib={'href': ("../entries/entry-%s.html" % entry['itemid'])})
        if comments_count > 1:
            comments_a.text = (u"%s comments" % comments_count)
        else:
            comments_a.text = u"1 comment"

    return wrapper


def resolve_cached_image_references(content, image_urls_to_filenames):
    # Find any image URLs
    urls_found = re.findall(r'img[^<>]*\ssrc\s?=\s?[\'\"](https?:/+[^\s\"\'()<>]+)[\'\"]', content, flags=re.IGNORECASE)
    # Build a regular expression to detect images hosted on Dreamwidth
    dw_hosted_pattern = re.compile('^https://(\w+).dreamwidth.org/file/\d+x\d+/(.+)')
    for image_url in urls_found:

        url_in_cache = image_url
        if dw_hosted_pattern.match(image_url):
            dw_hosted = dw_hosted_pattern.search(image_url)
            url_in_cache = 'https://' + dw_hosted.group(1) + '.dreamwidth.org/file/' + dw_hosted.group(2)

        if url_in_cache in image_urls_to_filenames:
            filename = image_urls_to_filenames[url_in_cache]
            content = content.replace(image_url, ("../images/%s" % filename))
    return content


def create_single_entry_page(journal_short_name, entry, comments, image_urls_to_filenames, icons_by_keyword, moods_by_id, previous_entry=None, next_entry=None):
    page, content = create_template_page(journal_short_name, "%s entry %s" % (journal_short_name, entry['itemid']))

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
                journal_short_name=journal_short_name,
                entry=entry,
                comments_count=len(comments),
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
    # broken HTML.  We can't rely on parsing a journal entry into XML and then
    # embedding it as elements.  There is also no clean way to slipstream string data
    # into the XML during the rendering process (it either gets parsed as usual before
    # insertion, or run through an escaper).  So we're going to render the document as
    # text right here, and then do a text search (a split) to find the div with id
    # "entry-content-insertion-point".  Then we'll interleave the entry contents and
    # re-assemble the document.  It's hacky but it avoids the need to police the HTML
    # skills of thousands of users whose entries render fine in Dreamwidth.
    html_as_string = ET.tostring(page, encoding="utf-8", method="html").decode('utf-8')
    html_split_on_entry_body = html_as_string.split(u'<div class="entry-content" id="entry-content-insertion-point"></div>')

    text_strings = []
    entry_body = entry['event']
    entry_body = resolve_cached_image_references(entry_body, image_urls_to_filenames)
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
        comment_body = re.sub("(\r\n|\r|\n)", "<br />", comment['body'])
        wrapped_comment_body = ("<div class=\"comment-content\" id=\"comment-content-%s-insertion-point\">" % comment['id']) + comment_body + "</div>"

        remainder = remainder.replace(marker, wrapped_comment_body, 1)

    text_strings.append(remainder)
    return ''.join(text_strings)


def create_history_page(journal_short_name, entries, comments_grouped_by_entry, image_urls_to_filenames, icons_by_keyword, moods_by_id, page_number, previous_page_entry_count=0, next_page_entry_count=0):
    page, content = create_template_page(journal_short_name, "%s entries page %s" % (journal_short_name, page_number))

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
                    journal_short_name=journal_short_name,
                    entry=entry,
                    comments_count=len(comments_grouped_by_entry[entry['itemid']]),
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
        entry_body = resolve_cached_image_references(entry_body, image_urls_to_filenames)
        entry_body = re.sub("(\r\n|\r|\n)", "<br />", entry_body)
        text_strings.append(html_split_on_insertion_points[i])
        text_strings.append(u'<div class="entry-content" id="entry-content-insertion-point">')
        text_strings.append(entry_body)
        text_strings.append(u'</div>')
    # Add the tail end of the rendered HTML
    text_strings.append(html_split_on_insertion_points[-1])

    return ''.join(text_strings)


def create_table_of_contents_page(journal_short_name, entry_count, entries_table_of_contents, history_page_table_of_contents, tags_encountered, entries_by_tag):
    page, content = create_template_page(journal_short_name, "%s archive" % journal_short_name)

    toc_banner = ET.SubElement(content, 'h1')
    toc_banner.text = 'Number of entries: %s' % entry_count

    history_toc_banner = ET.SubElement(content, 'h2')
    history_toc_banner.text = 'History Pages'

    history_ul = ET.SubElement(content, 'ul')

    for toc in history_page_table_of_contents:
        history_li = ET.SubElement(history_ul, 'li')
        history_a = ET.SubElement(history_li, 'a', attrib={ 'href': toc['filename'] })
        d_from = html.escape(toc['from'].strftime("%Y %b %e"))
        d_to = html.escape(toc['to'].strftime("%Y %b %e"))
        history_a.text = "%s ... %s" % (d_from, d_to)

    tag_toc_banner = ET.SubElement(content, 'h2')
    tag_toc_banner.text = 'Entries By Tag'

    for tag in tags_encountered:
        tag_banner_a = ET.SubElement(content, 'a', attrib={ 'name': tag, 'id': tag })
        tag_banner = ET.SubElement(tag_banner_a, 'h3')
        tag_banner.text = html.escape(tag)
        tag_ul = ET.SubElement(content, 'ul')

        for toc in entries_by_tag[tag]:
            tag_li = ET.SubElement(tag_ul, 'li')
            tag_a = ET.SubElement(tag_li, 'a', attrib={ 'href': toc['filename'] })
            d = toc['date']
            dh = int(f'{d:%I}')
            e_date = html.escape(f'{d:%b}. {d.day}, {d:%Y} {dh}:{d:%M} {d:%p}')
            tag_a.text = "%s:" % e_date
            tag_a.tail = " %s" % toc['subject']

    entries_toc_banner = ET.SubElement(content, 'h2')
    entries_toc_banner.text = 'All Entries By Month'

    for toc_group in entries_table_of_contents:
        month_banner = ET.SubElement(content, 'h4')
        month_banner.text = html.escape(toc_group[0]['date'].strftime("%Y %B"))
        month_ul = ET.SubElement(content, 'ul')

        for toc in toc_group:
            month_li = ET.SubElement(month_ul, 'li')
            month_a = ET.SubElement(month_li, 'a', attrib={ 'href': toc['filename'] })
            d = toc['date']
            dh = int(f'{d:%I}')
            e_date = html.escape(f'{d:%b}. {d.day}, {d:%Y} {dh}:{d:%M} {d:%p}')
            month_a.text = "%s:" % e_date
            month_a.tail = " %s" % toc['subject']

    html_as_string = ET.tostring(page, encoding="utf-8", method="html").decode('utf-8')
    return html_as_string


def download_entry_image(img_url, journal_short_name, subfolder, image_id, entry_url, ljuniq):
    try:
        headers = {}
        # A URL is not mandatory in the journal data, so we need to check that.
        if (entry_url is not None) and (ljuniq is not None):
            # Only necessary for Dreamwidth-hosted images, but does no harm generally.
            headers = {'Referer': entry_url, 'Cookie': "ljuniq="+ljuniq}

        image_req = urllib.request.urlopen(urllib.request.Request(img_url, headers = headers), timeout = 4)
        if image_req.headers.get_content_maintype() != 'image':
            print('Content type %s not expected, image skipped: %s' % (image_req.headers.get_content_maintype(), img_url))
            return (1, None)
        extension = MimeExtensions.get(image_req.info()["Content-Type"], "")

        # Try and decode any utf-8 in the URL
        try:
            filename = codecs.utf_8_decode(img_url)[0]
        except:
            # for installations where the above utf_8_decode doesn't work
            filename = "".join([ord(x) < 128 and x or "_" for x in img_url])
        # There may not be an extension we're familiar with present, but if there is, remove it
        filename = re.sub(r'(\.gif|\.jpg|\.jpeg|\.png)$', "", filename, flags=re.IGNORECASE)
        # Take the protocol off the URL
        filename = re.sub(r'^https?:/+', "", filename, flags=re.IGNORECASE)
        # Neutralize characters that don't look like a basic filename, and truncate it to the last 50 characters
        filename = re.sub(r'[*?\\/:\.\'<> "|]+', "_", filename[-50:] )
        filename = filename.lstrip("_")
        filename = "%s/%s-%s%s" % (subfolder, image_id, filename, extension)

        # Make sure our cache folder and subfolder exist
        try:
            os.mkdir("%s/images" % (journal_short_name))
        except OSError as e:
            if e.errno == 17:   # Folder already exists
                pass
        try:
            os.mkdir("%s/images/%s" % (journal_short_name, subfolder))
        except OSError as e:
            if e.errno == 17:   # Folder already exists
                pass

        # Copy the file stream directly into the file and close both
        pic_file = open("%s/images/%s" % (journal_short_name, filename), "wb")
        shutil.copyfileobj(image_req, pic_file)
        image_req.close()
        pic_file.close()
        return (0, filename)
    except urllib.error.HTTPError as e:
        print(e)
        return (e.code, None)
    except urllib.error.URLError as e:
        print(e)
        return (2, None)
    except Exception as e:
        print(e)
        return (1, None)


def ljdumptohtml(username, journal_short_name, ljuniq=None, verbose=True, cache_images=True, retry_images=True):
    if verbose:
        print("Starting conversion for: %s" % journal_short_name)

    conn = None
    cur = None

    # create a database connection
    conn = connect_to_local_journal_db("%s/journal.db" % journal_short_name, verbose)
    if not conn:
        print("Database could not be opened for journal %s" % journal_short_name)
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

    #
    # image caching
    #

    if cache_images:
        dw_hosted_pattern = re.compile('^https://(\w+).dreamwidth.org/file/\d+x\d+/(.+)')
        image_resolve_max = 200
        entry_index = 0
        while image_resolve_max > 0:
            if entry_index >= len(entries_by_date):
                image_resolve_max = 0
            else:
                entry = entries_by_date[entry_index]
                entry_index += 1
                e_id = entry['itemid']
                entry_date = datetime.utcfromtimestamp(entry['eventtime_unix'])
                entry_body = entry['event']
                urls_found = re.findall(r'<img[^<>]*\ssrc\s?=\s?[\'\"](https?:/+[^\s\"\'()<>]+)[\'\"]', entry_body, flags=re.IGNORECASE)
                subfolder = entry_date.strftime("%Y-%m")
                for image_url in urls_found:

                    url_to_cache = image_url
                    if dw_hosted_pattern.match(image_url):
                        dw_hosted = dw_hosted_pattern.search(image_url)
                        url_to_cache = 'https://' + dw_hosted.group(1) + '.dreamwidth.org/file/' + dw_hosted.group(2)

                    cached_image = get_or_create_cached_image_record(cur, verbose, url_to_cache, entry_date)
                    try_cache = True
                    # If a fetch was already attempted less than one day ago, don't try again
                    if cached_image['date_last_attempted']:
                        # Respect the global image cache setting
                        try_cache = retry_images
                        current_date = int(calendar.timegm(datetime.utcnow().utctimetuple()))
                        if int(current_date) - int(cached_image['date_last_attempted']) < 86400:
                            try_cache = False
                    # If we already have an image cached for this URL, skip it.
                    if (cached_image['cached'] == False) and try_cache:
                        image_id = cached_image['id']
                        cache_result = 0
                        img_filename = None
                        (cache_result, img_filename) = download_entry_image(url_to_cache, journal_short_name, subfolder, image_id, entry['url'], ljuniq)
                        if (cache_result == 0) and (img_filename is not None):
                            report_image_as_cached(cur, verbose, image_id, img_filename, entry_date)
                            image_resolve_max -= 1
                        else:
                            report_image_as_attempted(cur, verbose, image_id)

    all_cached = get_all_successfully_cached_image_records(cur, verbose)
    image_urls_to_filenames = {}
    for i in all_cached:
        image_urls_to_filenames[i['url']] = i['filename']

    #pprint.pprint(image_urls_to_filenames)
    #os._exit(os.EX_OK)

    #
    # Entry pages, one per entry.
    #

    print("Rendering %s entry pages..." % (len(entries_by_date)))

    try:
        os.mkdir("%s/entries" % (journal_short_name))
    except OSError as e:
        if e.errno == 17:   # Folder already exists
            pass

    entries_table_of_contents = []
    current_month_group = []
    current_year_and_month_str = None

    for i in range(0, len(entries_by_date)):
        entry = entries_by_date[i]
        entry_date = datetime.utcfromtimestamp(entry['eventtime_unix'])
        entry_year_and_month_str = entry_date.strftime("%Y-%m")

        # Used for building a table of contents later
        toc = {
            'date': entry_date,
            'subject': entry['subject'],
            'filename': ("entries/entry-%s.html" % entry['itemid'])
        }
        previous_entry = None
        if i > 0:
            previous_entry = entries_by_date[i-1]
            # If the month and year for this entry do not match the
            # month and year for the current group of entries, start a new one.
            if entry_year_and_month_str != current_year_and_month_str:
                entries_table_of_contents.append(current_month_group)
                current_month_group = []
                current_year_and_month_str = entry_year_and_month_str
        else:
            # If we're on the first entry, skip the month/year comparison
            current_year_and_month_str = entry_year_and_month_str
        current_month_group.append(toc)
    
        next_entry = None
        if i < len(entries_by_date) - 1:
            next_entry = entries_by_date[i+1]

        page = create_single_entry_page(
                    journal_short_name=journal_short_name,
                    entry=entry,
                    comments=comments_grouped_by_entry[entry['itemid']],
                    image_urls_to_filenames=image_urls_to_filenames,
                    icons_by_keyword=icons_by_keyword,
                    moods_by_id=moods_by_id,
                    previous_entry=previous_entry,
                    next_entry=next_entry
                )
        write_html("%s/entries/entry-%s.html" % (journal_short_name, entry['itemid']), page)

    entries_table_of_contents.append(current_month_group)

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
        os.mkdir("%s/history" % (journal_short_name))
    except OSError as e:
        if e.errno == 17:   # Folder already exists
            pass

    history_page_table_of_contents = []
    for i in range(0, len(groups_of_twenty)):
        previous_count = 0
        if i > 0:
            previous_count = len(groups_of_twenty[i-1])
        next_count = 0
        if i < len(groups_of_twenty) - 1:
            next_count = len(groups_of_twenty[i+1])

        current_group = groups_of_twenty[i]
        page = create_history_page(
                    journal_short_name=journal_short_name,
                    entries=current_group,
                    comments_grouped_by_entry=comments_grouped_by_entry,
                    image_urls_to_filenames=image_urls_to_filenames,
                    icons_by_keyword=icons_by_keyword,
                    moods_by_id=moods_by_id,
                    page_number=i+1,
                    previous_page_entry_count=previous_count,
                    next_page_entry_count=next_count
                )
        write_html("%s/history/page-%s.html" % (journal_short_name, i+1), page)

        # Used for building a table of contents later
        toc = {
            'from': datetime.utcfromtimestamp(current_group[0]['eventtime_unix']),
            'to': datetime.utcfromtimestamp(current_group[-1]['eventtime_unix']),
            'filename': "history/page-%s.html" % (i+1)
        }
        history_page_table_of_contents.append(toc)

    #
    # Organizing by tag
    #

    entries_by_tag = {}
    tags_encountered = []
    for entry in entries_by_date:
        taglist = entry['props_taglist']
        if taglist is not None:
            # Used for building a table of contents later
            toc = {
                'date': datetime.utcfromtimestamp(entry['eventtime_unix']),
                'subject': entry['subject'],
                'filename': ("entries/entry-%s.html" % entry['itemid'])
            }
            tags_split = taglist.split(', ')
            for tag in tags_split:
                if not (tag in entries_by_tag):
                    tags_encountered.append(tag)
                    entries_by_tag[tag] = []
                entries_by_tag[tag].append(toc)

    tags_encountered = sorted(tags_encountered)

    #
    # Table of contents page
    #

    page = create_table_of_contents_page(
            journal_short_name=journal_short_name,
            entry_count=len(entries_by_date),
            entries_table_of_contents=entries_table_of_contents,
            history_page_table_of_contents=history_page_table_of_contents,
            tags_encountered=tags_encountered,
            entries_by_tag=entries_by_tag,
        )
    write_html("%s/index.html" % journal_short_name, page)

    print("Copying support files...")

    # Copy the default stylesheet into the journal folder
    source = "stylesheet.css"
    dest = "%s/stylesheet.css" % (journal_short_name)
    shutil.copyfile(source, dest)
    # Copy a generic user icon into the journal folder
    source = "user.png"
    dest = "%s/user.png" % (journal_short_name)
    shutil.copyfile(source, dest)

    finish_with_database(conn, cur)

    print("Done!")


if __name__ == "__main__":
    args = argparse.ArgumentParser(description="Livejournal archive to html utility")
    args.add_argument("--quiet", "-q", action='store_false', dest='verbose',
                      help="reduce log output")
    args.add_argument("--cache_images", "-i", action='store_true', dest='cache_images',
                      help="build a cache of images referenced in entries")
    args.add_argument("--dont_retry_images", "-d", action='store_false', dest='retry_images',
                      help="don't retry images that failed to cache once already")
    args = args.parse_args()
    if os.access("ljdump.config", os.F_OK):
        config = xml.dom.minidom.parse("ljdump.config")
        username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
        journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
        if not journals:
            journals = [username]

        ljuniq = None
        # If a user is hosting images on Dreamwidth and using a config file, they will
        # put their cookie in the config file.  Asking for it every time would annoy users
        # who are not hosting images on Dreamwidth.
        if args.cache_images:
            ljuniq_els = config.documentElement.getElementsByTagName("ljuniq")
            if len(ljuniq_els) > 0:
                ljuniq = ljuniq_els[0].childNodes[0].data
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
        ljuniq = None
        if args.cache_images:
            ljuniq = getpass("ljuniq cookie (for Dreamwidth hosted image downloads, leave blank otherwise): ")
        print

    for journal in journals:
        ljdumptohtml(
            username=username,
            ljuniq=ljuniq,
            journal_short_name=journal,
            verbose=args.verbose,
            cache_images=args.cache_images,
            retry_images=args.retry_images
        )
