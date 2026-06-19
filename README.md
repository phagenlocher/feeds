# feeds

**feeds** is a lightweight desktop RSS/Atom **indexer**.

It fetches feed metadata, catalogs entries, and tracks read/unread state,
but never renders the content; delegating it to the browser. 

## Feed Discovery

When adding a feed it's often enough to just paste the domain of a blog or publication without finding the specific RSS/Atom URL.
You want to add `https://lobste.rs/` feeds but don't know where the correct URL is?
No problem.
Or do you only want to add the feed of a tag like `https://lobste.rs/t/compilers`?
Just paste it.
**feeds** tries to discover RSS/Atom feeds from arbitrary URLs and gives you a choice on which discovered feeds to add.

There is also special logic for adding feeds from:
* YouTube
* Medium
* Reddit
* Substack

## Why an indexer?

An _indexer_ is different from a _reader_ in that it only shows you the entries of a feed but doesn't display them.
The displaying is left to the system's browser.
Since many blogs feature their own design and often some JavaScript-powered features, it only makes sense to delegate the display of posts to browsers and not handle that internally.
This program is only about keeping track of what feed entries you have seen or not.

## Quick start

You can download binaries from the [releases](https://github.com/phagenlocher/feeds/releases) page.

Alternatively, you can clone and run the app:

```sh
just run        # launch the app
```
