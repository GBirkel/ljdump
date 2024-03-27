# ljdump # 

**A Livejournal or Dreamwidth archive tool**

This program reads the journal entries from a Livejournal or Dreamwidth (or compatible) blog site and archives them in a subdirectory named after the journal name.

It keeps track of where it left off the last time it was run, so the next time you run it, it will only fetch the entries and comments that have changed.

__Note that to get the full archive of a very large journal, you may need to run the script a few times in a row, until it says there are no new changes.__

The simplest way to run this is to execute the ljdump.py script with Python. Depending on your OS, you may be able to double-click the ljdump.py script directly, or you may need to open a Terminal/Command Prompt window to run it. Either way, it will prompt you for your Livejournal username and password, then download all your journal entries, comments, and userpics.

You may optionally download entries from a different journal (a community) where you are a member. If you are a community maintainer, you can also download comments from the community.

### Using the configuration file ###

If you want to save your username and password so you don't have to type it every time you run ljdump, you can save it in the configuration file.

The configuration is read from "ljdump.config". A sample configuration is provided in "ljdump.config.sample", which should be copied and then edited.

The configuration settings are:

* __server__ - The XMLRPC server URL.

  This should only need to be changed if you are dumping a journal that is livejournal-compatible but is not livejournal itself.

* __username__ - The livejournal user name.

  A subdirectory will be created with this same name to store the journal entries.

* __password__ - The account password.

  This password is sent in the clear, so if you specify an alternative server, ensure you use a URL starting with https:// so the connection is encrypted. If not provided here, will prompt for it when run.

* __journal__ - Optional: The journal to download entries from.

  If this is not specified, the "username" journal is downloaded. If this is specified, then only the named journals will be downloaded.  This element may be specified more than once to download multiple journals.

### Command line options ###

  --quiet

Makes the script print far less status information to the console as it runs.

  --nosql

By defualt, this script writes everything (entries, comments, icon info) to a SQLite database instead of to individual files.  This flag turns that functionality off, and reverts to the old method of storing everything in individually numbered XML files.

  --fifty

Only fetch 50 of the entries that are new since the last sync, then stop.  Useful for testing the script output.

A Livejournal [community](https://ljdump.livejournal.com) was set up for questions or comments, on the original version of this code, but it has not seen attention for years.