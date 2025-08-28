from typing import List
import feedparser

def rss_to_urls(rss_urls: List[str], limit_per_feed: int = 10) -> List[str]:
    urls = []
    for feed_url in rss_urls:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:limit_per_feed]:
                link = getattr(entry, "link", None)
                if link:
                    urls.append(link)
        except Exception:
            continue
    return list(dict.fromkeys(urls))

