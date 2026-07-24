import asyncio
from typing import List, Dict, Optional

def calculate_discount(price: float, discount_rate: float=0.1, tax_rate: float=0.05) -> float:
    """Auto-generated Google docstring for calculate_discount.

Args:
    *args: Function arguments.

Returns:
    Any: Function result."""
    discounted = price * (1 - discount_rate)
    total = discounted * (1 + tax_rate)
    return round(total, 2)

def filter_valid_users(users: List[Dict[str, str]], min_age: int=18) -> List[Dict[str, str]]:
    """This function already has a docstring and should be skipped."""
    valid_users = []
    for user in users:
        if user.get('age', 0) >= min_age:
            valid_users.append(user)
    return valid_users

async def fetch_api_data(endpoint: str, timeout: int=10) -> Optional[dict]:
    """Auto-generated Google docstring for fetch_api_data.

Args:
    *args: Function arguments.

Returns:
    Any: Function result."""
    await asyncio.sleep(0.1)
    return {'status': 200, 'data': f'response from {endpoint}'}

class DataProcessor:

    def __init__(self, name: str):
        """Auto-generated Google docstring for __init__.

Args:
    *args: Function arguments.

Returns:
    Any: Function result."""
        self.name = name

    def process_records(self, records: List[dict]) -> int:
        """Auto-generated Google docstring for process_records.

Args:
    *args: Function arguments.

Returns:
    Any: Function result."""
        processed_count = 0
        for record in records:
            if 'id' in record:
                processed_count += 1
        return processed_count