import sys
import feedparser
import requests
import json
import re
from typing import List, Dict
import mysql.connector
import os
import os.path
from dotenv import load_dotenv
import tempfile
from datetime import datetime, timezone

load_dotenv()

BLOGGER_RSS_URL=os.getenv("BLOGGER_RSS_URL")

access_token=os.getenv("BSKY_ACCESS_TOKEN")
access_token_secret=os.getenv("BKSY_ACCESS_SECRET_TOKEN")
consumer_key=os.getenv("BSKY_API_KEY")
consumer_secret=os.getenv("BSKY_API_SECRET_KEY")

BLUESKY_HANDLE = os.getenv("BLUESKY_HANDLE") 
BLUESKY_APP_PASSWORD=os.getenv("BLUESKY_APP_PASSWORD")
DATABASE_FILE = "blogger_posts.db"

MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'blogger_user',
    'password': 'your_password',
    'database': 'blogger_posts_db'
}

def parse_mentions(text: str) -> List[Dict]:
    spans = []
    # regex based on: https://atproto.com/specs/handle#handle-identifier-syntax
    mention_regex = rb"[$|\W](@([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(mention_regex, text_bytes):
        spans.append({
            "start": m.start(1),
            "end": m.end(1),
            "handle": m.group(1)[1:].decode("UTF-8")
        })
    return spans

def parse_urls(text: str) -> List[Dict]:
    spans = []
    # partial/naive URL regex based on: https://stackoverflow.com/a/3809435
    # tweaked to disallow some training punctuation
    url_regex = rb"[$|\W](https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*[-a-zA-Z0-9@%_\+~#//=])?)"
    text_bytes = text.encode("UTF-8")
    for m in re.finditer(url_regex, text_bytes):
        spans.append({
            "start": m.start(1),
            "end": m.end(1),
            "url": m.group(1).decode("UTF-8"),
        })
    return spans

def create_database():
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS processed_posts_bsky (id TEXT PRIMARY KEY);")
    connection.commit()
    connection.close()

def get_processed_posts():
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM processed_posts_bsky;")
    processed_posts = [row[0] for row in cursor.fetchall()]
    print(processed_posts)
    connection.close()
    return processed_posts

def mark_post_as_processed(post_id):
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor()
    cursor.execute("INSERT INTO processed_posts_bsky (id) VALUES (%s);", (post_id,))  # <-- Use a tuple (post_id,)
    connection.commit()
    connection.close()

def parse_facets(text: str) -> List[Dict]:
    facets = []
    for m in parse_mentions(text):
        resp = requests.get(
            "https://bsky.social/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": m["handle"]},
        )
        # If the handle can't be resolved, just skip it!
        # It will be rendered as text in the post instead of a link
        if resp.status_code == 400:
            continue
        did = resp.json()["did"]
        facets.append({
            "index": {
                "byteStart": m["start"],
                "byteEnd": m["end"],
            },
            "features": [{"$type": "app.bsky.richtext.facet#mention", "did": did}],
        })
    for u in parse_urls(text):
        facets.append({
            "index": {
                "byteStart": u["start"],
                "byteEnd": u["end"],
            },
            "features": [
                {
                    "$type": "app.bsky.richtext.facet#link",
                    # NOTE: URI ("I") not URL ("L")
                    "uri": u["url"],
                }
            ],
        })
    return facets

# Blogger RSS feed URL
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

post = {
    "$type": "app.bsky.feed.post",
    "text": "Hello World!",
    "createdAt": now,
}

def get_latest_blogger_post():
    feed = feedparser.parse(BLOGGER_RSS_URL)
    if feed.entries:
        latest_post = feed.entries[0]
        return latest_post
    return None

def extract_image_url(content):
    # Simple extraction logic, replace with your actual logic
    # This assumes the image URL is in the src attribute of an <img> tag
    image_tag_start = content.find('<img')
    if image_tag_start != -1:
        src_start = content.find('src="', image_tag_start)
        if src_start != -1:
            src_end = content.find('"', src_start + 5)
            if src_end != -1:
                return content[src_start + 5:src_end]

    return None

def download_image(image_url, local_filename):
    response = requests.get(image_url, stream=True)
    if response.status_code == 200:
        with open(local_filename, 'wb') as image_file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    image_file.write(chunk)
    else:
        print(f"Failed to download image. Status Code: {response.status_code}")
    size=os.path.getsize(local_filename)
    return(size)

def repost_to_bluesky(post):
    # Assuming Bluesky API requires POST request with access token
    headers = {
        "Authorization": f"Bearer {BLUESKY_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    # Assuming Bluesky API expects specific parameters
    data = {
        "title": post.title,
        "content": post.summary,
        # Add other necessary parameters based on Bluesky API
    }

    # Open and send the image file
#    with open("path/to/your/image.png", "rb") as image_file:
#        files = {"image": ("image.png", image_file, "image/png")}
#        response = requests.post(BLUESKY_API_ENDPOINT, data=data, headers=headers, files=files)

#    response = requests.post(BLUESKY_API_ENDPOINT, json=data, headers=headers)

    if response.status_code == 200:
        print("Reposted successfully to Bluesky!")
    else:
        print(f"Failed to repost. Status Code: {response.status_code}, Response: {response.text}")

def main():
    latest_blogger_post = get_latest_blogger_post()
    if latest_blogger_post:
        post_id = latest_blogger_post.id
        processed_posts = get_processed_posts()
        print(processed_posts)
        if post_id not in processed_posts:
            print(post_id  + ' is already posted')

        if post_id not in processed_posts:# or True:
            mark_post_as_processed(post_id)
            post['text']=latest_blogger_post['title'] + ' ' + \
                latest_blogger_post['link']
            post["facets"] = parse_facets(post["text"])
            post_content=latest_blogger_post.content[0]
            image_url = extract_image_url(post_content['value'])
            if image_url is not None:
                image_extension=image_url.split('.')[-1]
                mimeType='image/' + image_extension
                local_image_filename = "/tmp/image_blogger." + image_extension
                if os.path.exists(local_image_filename):
                    os.system('rm ' + local_image_filename)
                image_size=download_image(image_url, local_image_filename)
                
            resp = requests.post(
                "https://bsky.social/xrpc/com.atproto.server.createSession",
                json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
            )
            resp.raise_for_status()
            session = resp.json()

            if image_url is not None:
                with open(local_image_filename, "rb") as f:
                    img_bytes = f.read()
                if os.path.exists(local_image_filename):
                    os.system('rm ' + local_image_filename)

                resp = requests.post(
                    "https://bsky.social/xrpc/com.atproto.repo.uploadBlob",
                    headers={
                        "Content-Type": mimeType,
                        "encoding": mimeType,
                        "Authorization": "Bearer " + session["accessJwt"],
                    },
                    data=img_bytes,
                )
                resp.raise_for_status()
                blob = resp.json()["blob"]
                print('blob')
                print(blob)
                post["embed"] = {
                    "$type": "app.bsky.embed.images",
                    "images": [{
                         "alt": 'Graphical abstract for article',
                         "image": blob,
                     }],
                     }

            json={
                "repo": session["did"],
                "collection": "app.bsky.feed.post",
                "record": post,
            }

            resp = requests.post(
                "https://bsky.social/xrpc/com.atproto.repo.createRecord",
                headers={"Authorization": "Bearer " + session["accessJwt"]},
                json=json)
            resp.raise_for_status()
            print(resp)

        else:
            print("Post already processed.")
    else:
        print("No new posts on the Blogger RSS feed.")

    
if __name__ == "__main__":
    main()
