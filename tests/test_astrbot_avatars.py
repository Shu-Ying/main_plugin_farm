import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]


class AvatarTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'farm_astrbot_avatars',
            ROOT / 'integrations/astrbot/avatars.py',
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.cache = self.module.AvatarCache()

    async def asyncTearDown(self):
        await self.cache.close()

    async def test_avatar_success_cache_and_concurrent_requests(self):
        async def download(user_id):
            await asyncio.sleep(0)
            return b'avatar'

        with patch.object(self.module, 'download_avatar',
                          side_effect=download) as fetch:
            results = await asyncio.gather(*(
                self.cache.get('aiocqhttp', '123456') for _ in range(8)
            ))
            self.assertEqual(results, [b'avatar'] * 8)
            self.assertEqual(
                await self.cache.get('aiocqhttp', '123456'), b'avatar',
            )
            fetch.assert_awaited_once_with('123456')
            self.assertEqual(
                await self.cache.get('aiocqhttp', '654321'), b'avatar',
            )
            self.assertEqual(fetch.await_count, 2)

    async def test_failure_negative_cache_and_expiry(self):
        with patch.object(self.module, 'download_avatar',
                          new=AsyncMock(side_effect=OSError('offline'))) as f:
            with patch.object(self.module, 'monotonic', return_value=0):
                self.assertIsNone(await self.cache.get('aiocqhttp', '12345'))
            with patch.object(self.module, 'monotonic', return_value=20):
                self.assertIsNone(await self.cache.get('aiocqhttp', '12345'))
            self.assertEqual(f.await_count, 1)
            with patch.object(self.module, 'monotonic', return_value=31):
                self.assertIsNone(await self.cache.get('aiocqhttp', '12345'))
            self.assertEqual(f.await_count, 2)

    async def test_unknown_platform_invalid_id_and_closed_cache(self):
        with patch.object(self.module, 'download_avatar') as fetch:
            for platform, user in (
                ('telegram', '12345'), ('qq_official', '12345'),
                ('aiocqhttp', '../secret'), ('aiocqhttp', '１２３４５'),
                ('aiocqhttp', ''), ('aiocqhttp', '1' * 21),
            ):
                self.assertIsNone(await self.cache.get(platform, user))
            await self.cache.close()
            self.assertIsNone(await self.cache.get('aiocqhttp', '12345'))
            fetch.assert_not_called()

    async def test_timeout_size_and_cache_bound(self):
        async def slow(user_id):
            await asyncio.sleep(10)

        with patch.object(self.module, 'FETCH_TIMEOUT', 0.01):
            with patch.object(self.module, 'download_avatar', side_effect=slow):
                self.assertIsNone(await self.cache.get('aiocqhttp', '12345'))
        with patch.object(self.module, 'download_avatar', new=AsyncMock(
                return_value=b'x' * (self.module.MAX_BYTES + 1))):
            self.assertIsNone(await self.cache.get('aiocqhttp', '54321'))
        with patch.object(self.module, 'download_avatar',
                          new=AsyncMock(return_value=b'avatar')):
            for index in range(30):
                await self.cache.get('aiocqhttp', str(100000 + index))
        self.assertLessEqual(len(self.cache._cache), 16)

    async def test_close_and_independent_caller_cancellation(self):
        started, finish = asyncio.Event(), asyncio.Event()

        async def download(user_id):
            started.set()
            await finish.wait()
            return b'avatar'

        with patch.object(self.module, 'download_avatar', side_effect=download):
            first = asyncio.create_task(self.cache.get('aiocqhttp', '12345'))
            await started.wait()
            second = asyncio.create_task(self.cache.get('aiocqhttp', '12345'))
            await asyncio.sleep(0)
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            finish.set()
            self.assertEqual(await second, b'avatar')
            started.clear()
            finish.clear()
            third = asyncio.create_task(self.cache.get('aiocqhttp', '54321'))
            await started.wait()
            await self.cache.close()
            with self.assertRaises(asyncio.CancelledError):
                await third
            self.assertFalse(self.cache._pending)
            self.assertFalse(self.cache._cache)

    async def test_downloader_stream_limit_and_no_redirect(self):
        class Body:
            async def iter_chunked(self, size):
                yield b'a' * (self_limit + 1)

        self_limit = self.module.MAX_BYTES

        class Response:
            status = 200
            content_length = None
            content = Body()

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class Session(Response):
            def get(self, url, **kwargs):
                self_url.append((url, kwargs))
                return Response()

        self_url = []
        with patch.object(self.module.aiohttp, 'ClientSession',
                          return_value=Session()):
            self.assertIsNone(await self.module.download_avatar('12345'))
        self.assertEqual(self_url[0][0],
                         'https://q1.qlogo.cn/g?b=qq&nk=12345&s=100')
        self.assertFalse(self_url[0][1]['allow_redirects'])
