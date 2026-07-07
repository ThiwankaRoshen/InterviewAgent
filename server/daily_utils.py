import httpx
from loguru import logger
import time 

from settings import settings

async def create_daily_token(room_name: str, is_owner: bool = True) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.DAILY_API_URL}/meeting-tokens",
            headers={
                "Authorization": f"Bearer {settings.DAILY_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "properties": {
                    "room_name": room_name,
                    "is_owner": is_owner,
                    "exp": int(time.time()) + 3600,
                }
            }
        )
        response.raise_for_status()
        return response.json()["token"]
    
async def create_daily_room() -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.DAILY_API_URL}/rooms",
            headers={
                "Authorization": f"Bearer {settings.DAILY_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "properties": {
                    "enable_prejoin_ui": False,
                    "enable_screenshare": False,
                    "enable_chat": False,
                    "start_video_off": True,
                    "start_audio_off": False,
                    "exp": int(time.time()) + 3600 ,
                }
            }
        )
        response.raise_for_status()
        return response.json()


async def delete_daily_room(room_url: str):
    room_name = room_url.split("/")[-1]
    async with httpx.AsyncClient() as client:
        try:
            await client.delete(
                f"{settings.DAILY_API_URL}/rooms/{room_name}",
                headers={"Authorization": f"Bearer {settings.DAILY_API_KEY}"}
            )
        except Exception as e:
            logger.warning(f"Failed to delete room: {e}")
            raise e
