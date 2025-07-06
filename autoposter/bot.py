import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel
from datetime import datetime
import schedule
import time
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import logging


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


load_dotenv()


DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./posts.db')
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Post(Base):
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True, index=True)
    content = Column(String)
    scheduled_time = Column(DateTime)
    status = Column(String, default='pending')  # pending, posted, failed

Base.metadata.create_all(bind=engine)


API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')

client = TelegramClient('bot', API_ID, API_HASH)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def post_to_channel(content, channel_id):
    try:
        channel = PeerChannel(int(channel_id))
        async with client:
            await client.send_message(channel, content)
        return True
    except Exception as e:
        logger.error(f"Error posting to channel: {str(e)}")
        return False

def check_and_post_scheduled():
    db = next(get_db())
    try:
        current_time = datetime.now()
        posts = db.query(Post).filter(
            Post.scheduled_time <= current_time,
            Post.status == 'pending'
        ).all()
        
        for post in posts:
            if post_to_channel(post.content, CHANNEL_ID):
                post.status = 'posted'
            else:
                post.status = 'failed'
            db.commit()
    except Exception as e:
        logger.error(f"Error checking scheduled posts: {str(e)}")
    finally:
        db.close()

async def handle_new_post(event):
    try:
        db = next(get_db())
        content = event.text
        scheduled_time = datetime.now() + timedelta(minutes=1)
        
        new_post = Post(
            content=content,
            scheduled_time=scheduled_time
        )
        
        db.add(new_post)
        db.commit()
        
        await event.reply(f"Post scheduled for {scheduled_time}")
    except Exception as e:
        logger.error(f"Error handling new post: {str(e)}")
        await event.reply("Error occurred while scheduling the post")

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.reply("Привет! Я бот для автоматической публикации сообщений в канал. Просто отправьте сообщение, и я запланирую его публикацию.")

@client.on(events.NewMessage)
async def handle_message(event):
    if event.message.text and not event.message.text.startswith('/'):
        await handle_new_post(event)

if __name__ == "__main__":
    
    schedule.every(1).minutes.do(check_and_post_scheduled)
    
    
    with client:
        client.run_until_disconnected()
    
    
    while True:
        schedule.run_pending()
        time.sleep(1)
