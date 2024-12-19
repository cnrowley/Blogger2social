import sys
import feedparser
import requests
import json
import re
from typing import List, Dict
import mysql.connector
import os
import os.path
import tweepy
from dotenv import load_dotenv
import tempfile

load_dotenv()

BLOGGER_RSS_URL=os.getenv("BLOGGER_RSS_URL")

access_token=os.getenv("TWITTER_ACCESS_TOKEN")
access_token_secret=os.getenv("TWITTER_ACCESS_SECRET_TOKEN")
consumer_key=os.getenv("TWITTER_API_KEY")
consumer_secret=os.getenv("TWITTER_API_SECRET_KEY")


MYSQL_CONFIG = {
    'host': 'localhost',
    'user': 'blogger_user',
    'password': 'your_password',
    'database': 'blogger_posts_db'
}

from datetime import datetime, timezone
DATABASE_FILE = "blogger_posts.db"


def create_database():
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS processed_posts (id TEXT PRIMARY KEY);")
    connection.commit()
    connection.close()

def get_processed_posts():
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM processed_posts;")
    processed_posts = [row[0] for row in cursor.fetchall()]
    connection.close()
    return processed_posts

def mark_post_as_processed(post_id):
    connection = mysql.connector.connect(**MYSQL_CONFIG)
    cursor = connection.cursor()
    cursor.execute("INSERT INTO processed_posts_chemfacultycdn_twitter (id) VALUES (%s);", (post_id,))  # <-- Use a tuple (post_id,)
    connection.commit()
    connection.close()


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

def post_to_twitter(title, link, image_url=None):
    status_text = f"{title} {link}"
 
    client = tweepy.Client(consumer_key=consumer_key,consumer_secret=consumer_secret,access_token=access_token,access_token_secret=access_token_secret)

    client.create_tweet(text=status_text)

def main():
    latest_blogger_post = get_latest_blogger_post()
    if latest_blogger_post:
        post_id = latest_blogger_post.id
        processed_posts = get_processed_posts()
        print(post_id)
        print()
        print(processed_posts)
        if post_id in processed_posts:
            print(post_id  + ' is already posted')

        if post_id not in processed_posts: # or True
            post_to_twitter(latest_blogger_post['title'], latest_blogger_post['link'])
        mark_post_as_processed(post_id)
    
if __name__ == "__main__":
    main()
