import discord
import requests
from discord.ext import commands
from discord.ext.commands import Cog
from bot.core import Bot, Context
from bs4 import BeautifulSoup
import asyncio, random
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import yt_dlp
import os
import aiohttp
import tempfile
from io import BytesIO

class Api(Cog):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.api_token = 'A8MGr2JCBZxe3TuY'  # Your EnsembleData API token

    # Function to fetch TikTok user posts
    def get_tiktok_user_posts(self, username: str):
        root = "https://ensembledata.com/apis"
        endpoint = "/tt/user/posts"
        params = {
            "username": username,
            "depth": 1,
            "start_cursor": 0,
            "oldest_createtime": 1667843879,  # Adjust the timestamp as needed
            "alternative_method": False,
            "token": self.api_token
        }
        response = requests.get(root + endpoint, params=params)
        return response.json()

    # Command to fetch TikTok user posts
    @commands.command(name='tiktokposts')
    async def fetch_tiktok_user_posts(self, ctx: Context, username: str):
        data = self.get_tiktok_user_posts(username)

        # Check if the 'data' key exists and handle missing fields
        if 'data' in data and data['data']:
            posts = data['data']
            embed = discord.Embed(title=f"Posts from {username}", url=f'https://www.tiktok.com/@{username}')
            
            # Add each post to the embed
            for post in posts:
                post_description = post.get('desc', 'No description')
                post_url = f"https://www.tiktok.com/@{username}/video/{post.get('id', 'N/A')}"
                embed.add_field(name='Post', value=f"[{post_description}]({post_url})", inline=False)
            
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Could not find posts for user @{username} or no posts available.")
            

class PinterestScraper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



    @commands.command(name="scrape")
    async def scrape_pinterest(self, ctx, board_url: str):
        await ctx.send(f"Starting to scrape images and videos from Pinterest board: {board_url}")
        
        # Get all images and videos from Pinterest (no filtering or exclusion)
        image_urls, video_urls = self.get_pinterest_media(board_url)
        
        if not image_urls and not video_urls:
            await ctx.send("No images or videos found or an error occurred during scraping.")
            return
        
        # Post all images and videos to the Discord channel
        await self.post_media_to_discord(ctx, image_urls, video_urls)

    def get_pinterest_media(self, board_url):
        # List of different User-Agent strings to rotate during each scrape
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
            'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:40.0) Gecko/20100101 Firefox/40.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36 Edge/90.0.818.56',
            'Mozilla/5.0 (Linux; Android 10; Pixel 3 XL) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Mobile Safari/537.36',
            'Mozilla/5.0 (Linux; Android 8.1.0; Nexus 5X Build/OPM7.181205.001) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.137 Mobile Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.125 Safari/537.36 Edge/84.0.522.63',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_4_2 like Mac OS X) AppleWebKit/537.36 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/537.36'
        ]
        
        user_agent = random.choice(user_agents)
        headers = {'User-Agent': user_agent}
        
        # Send a GET request to the Pinterest board URL
        response = requests.get(board_url, headers=headers)
        
        if response.status_code != 200:
            print(f"Failed to retrieve the page. Status code: {response.status_code}")
            return [], []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract image URLs (same as before)
        images = soup.find_all('img', {'src': True})
        img_urls = [
            img['src'] for idx, img in enumerate(images)
            if img['src'].startswith('https://') and not self.is_profile_picture(img['src']) and idx != 0
        ]
        
        # Extract video URLs (look for <video> or <iframe> tags that contain video sources)
        video_urls = []
        videos = soup.find_all('video')
        
        for video in videos:
            # Look for <source> tags inside <video> tags
            sources = video.find_all('source')
            for source in sources:
                if source.get('src'):
                    video_urls.append(source['src'])
        
        # Alternatively, look for <iframe> or other video hosting platforms
        iframes = soup.find_all('iframe', {'src': True})
        for iframe in iframes:
            src = iframe['src']
            if 'youtube' in src or 'vimeo' in src:  # Add other video platforms if needed
                video_urls.append(src)
        
        return img_urls, video_urls

    def is_profile_picture(self, url):
        """
        Filters out URLs that are likely the user's profile picture.
        You can modify this based on the URL pattern for profile pictures.
        """
        return 'profile' in url or 'avatar' in url

    async def post_media_to_discord(self, ctx, image_urls, video_urls):
        batch_size = 10
        media_batch = []

        # Process image URLs
        for idx, url in enumerate(image_urls):
            try:
                img_data = requests.get(url).content
                image_file = BytesIO(img_data)
                file = discord.File(image_file, filename=f"image_{idx + 1}.jpg")
                media_batch.append(file)

                if len(media_batch) == batch_size:
                    await ctx.send(files=media_batch)
                    media_batch = []
                
                await asyncio.sleep(2)  # Prevent hitting rate limits

            except Exception as e:
                print(f"Error posting image: {e}")
                await ctx.send("Error posting image.")
        
        # Process video URLs
        for idx, video_url in enumerate(video_urls):
            try:
                # You can fetch the video URL and use it directly if it's publicly accessible
                video_file = discord.File(video_url, filename=f"video_{idx + 1}.mp4")
                media_batch.append(video_file)

                if len(media_batch) == batch_size:
                    await ctx.send(files=media_batch)
                    media_batch = []
                
                await asyncio.sleep(2)  # Prevent hitting rate limits

            except Exception as e:
                print(f"Error posting video: {e}")
                await ctx.send("Error posting video.")
        
        # Send remaining media (images and videos)
        if media_batch:
            await ctx.send(files=media_batch)



class XTweet(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def extract_info(self, url: str) -> dict:
        ydl_opts = {
            'quiet': True,
            'skip_download': False,
            'format': 'best[ext=mp4]/best[ext=jpg]/best',
            'outtmpl': 'xtweet.%(ext)s',
            'noplaylist': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=True)

    @commands.command(name="xtweet", usage="xtweet <tweet_url>")
    async def xtweet(self, ctx: Context, url: str):
        """Download and post a tweet's media (video/image) + metadata in embed."""
        await ctx.typing()

        try:
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, self.extract_info, url)

            # Metadata
            uploader = info.get("uploader", "Unknown")
            tweet_text = info.get("title", "No text found")
            upload_date = info.get("upload_date")
            like_count = info.get("like_count")
            view_count = info.get("view_count")
            duration = info.get("duration")
            tweet_url = info.get("webpage_url")
            thumbnail = info.get("thumbnail")

            if upload_date:
                upload_date = datetime.strptime(upload_date, "%Y%m%d").strftime("%B %d, %Y")

            embed = discord.Embed(
                title=f"@{uploader}'s Tweet",
                description=tweet_text[:4096],
                color=0x1DA1F2,
                url=tweet_url
            )
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            if upload_date:
                embed.add_field(name="📅 Date", value=upload_date, inline=True)
            if like_count is not None:
                embed.add_field(name="❤️ Likes", value=f"{like_count:,}", inline=True)
            if view_count is not None:
                embed.add_field(name="👁️ Views", value=f"{view_count:,}", inline=True)
            if duration is not None:
                mins, secs = divmod(duration, 60)
                embed.add_field(name="⏱️ Duration", value=f"{mins}m {secs}s", inline=True)

            # Determine downloaded file
            media_file = None
            for ext in ("mp4", "jpg", "jpeg", "png", "webp"):
                path = f"xtweet.{ext}"
                if os.path.exists(path):
                    media_file = path
                    break

            # Send metadata
            await ctx.send(embed=embed)

            # Send media
            if media_file:
                await ctx.send(file=discord.File(media_file))
                os.remove(media_file)
            else:
                await ctx.warn("Media could not be downloaded.")

        except Exception as e:
            await ctx.warn(f"Failed to fetch tweet: `{e}`")


async def setup(bot: Bot) -> None:
    await bot.add_cog(Api(bot))
    await bot.add_cog(PinterestScraper(bot))
    await bot.add_cog(XTweet(bot))