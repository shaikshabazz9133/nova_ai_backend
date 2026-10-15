
import asyncio

from database import create_tables, engine


async def main():
    try:
        await create_tables()
        print("Database tables created successfully!")
    except Exception as error:
        print(f"Table creation failed: {error}")
    finally:
        await engine.dispose()


asyncio.run(main())
