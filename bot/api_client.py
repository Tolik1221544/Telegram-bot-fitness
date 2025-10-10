import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from bot.config import config
import logging

logger = logging.getLogger(__name__)


class APIClient:
    """Client for FitnessTracker API"""

    def __init__(self):
        self.base_url = config.API_BASE_URL
        self.timeout = aiohttp.ClientTimeout(total=config.API_TIMEOUT)

    async def _request(self, method: str, endpoint: str,
                       headers: Optional[Dict] = None,
                       json_data: Optional[Dict] = None,
                       params: Optional[Dict] = None) -> Dict[Any, Any]:
        """Make API request"""
        url = f"{self.base_url}{endpoint}"

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                async with session.request(
                        method,
                        url,
                        headers=headers,
                        json=json_data,
                        params=params
                ) as response:
                    data = await response.json()

                    if response.status >= 400:
                        logger.error(f"API error: {response.status} - {data}")
                        raise Exception(f"API error: {data.get('error', 'Unknown error')}")

                    return data

            except asyncio.TimeoutError:
                logger.error(f"API timeout: {endpoint}")
                raise Exception("API request timeout")
            except Exception as e:
                logger.error(f"API request failed: {e}")
                raise

    # Authentication
    async def send_verification_code(self, email: str) -> bool:
        """Send verification code to email"""
        result = await self._request(
            'POST',
            '/api/auth/send-code',
            json_data={'email': email}
        )
        return result.get('success', False)

    async def confirm_email(self, email: str, code: str) -> Dict:
        """Confirm email with code"""
        return await self._request(
            'POST',
            '/api/auth/confirm-email',
            json_data={'email': email, 'code': code}
        )

    # User management
    async def get_user_profile(self, token: str) -> Dict:
        """Get user profile"""
        return await self._request(
            'GET',
            '/api/user/profile',
            headers={'Authorization': f'Bearer {token}'}
        )

    async def update_user_profile(self, token: str, data: Dict) -> Dict:
        """Update user profile"""
        return await self._request(
            'PUT',
            '/api/user/profile',
            headers={'Authorization': f'Bearer {token}'},
            json_data=data
        )

    # Coins management
    async def get_balance(self, token: str) -> Dict:
        """Get user's coin balance"""
        return await self._request(
            'GET',
            '/api/lw-coin/balance',
            headers={'Authorization': f'Bearer {token}'}
        )

    async def set_balance(self, token: str, amount: int, source: str = 'manual') -> Dict:
        """Set user's coin balance (admin)"""
        return await self._request(
            'POST',
            '/api/lw-coin/set-balance',
            headers={'Authorization': f'Bearer {token}'},
            json_data={'amount': amount, 'source': source}
        )

    async def purchase_subscription(self, token: str, coins: int, days: int, price: float) -> Dict:
        """Purchase subscription with coins"""
        return await self._request(
            'POST',
            '/api/lw-coin/purchase-subscription',
            headers={'Authorization': f'Bearer {token}'},
            json_data={
                'coinsAmount': coins,
                'durationDays': days,
                'price': price
            }
        )

    async def get_transactions(self, token: str) -> List[Dict]:
        """Get user's coin transactions"""
        return await self._request(
            'GET',
            '/api/lw-coin/transactions',
            headers={'Authorization': f'Bearer {token}'}
        )

    # Stats
    async def get_user_stats(self, token: str) -> Dict:
        """Get user statistics"""
        return await self._request(
            'GET',
            '/api/stats/user',
            headers={'Authorization': f'Bearer {token}'}
        )
    async def check_payment_status(self, order_id: str) -> Dict:
        """Check payment status"""
        return await self._request(
            'GET',
            f'/api/payment/check/{order_id}'
        )
    async def create_pending_payment(self, order_id: str, telegram_id: int, amount: float,
                                     currency: str, package_id: str, coins_amount: int, duration_days: int):
        """Create pending payment on backend"""
        return await self._request(
            'POST',
            '/api/tribute-pending/create',
            json_data={
                'orderId': order_id,
                'telegramId': telegram_id,
                'amount': amount,
                'currency': currency,
                'packageId': package_id,
                'coinsAmount': coins_amount,
                'durationDays': duration_days
            }
        )
api_client = APIClient()