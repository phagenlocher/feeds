# feeds

**feeds** is a lightweight desktop RSS/Atom **indexer**.

It fetches feed metadata, catalogs entries, and tracks read/unread state,
but never renders the content; delegating it to the browser. 

## Why an indexer?

An _indexer_ is different from a _reader_ in that it only shows you the entries of a feed but doesn't display them.
The displaying is left to the system's browser.
Since many blogs feature their own design and often some JavaScript-powered features, it only makes sense to delegate the display of posts to browsers and not handle that internally.
This program is only about keeping track of what feed entries you have seen or not.

## Quick start

```sh
just run        # launch the app
just build      # build a standalone binary (dist/main)
```
