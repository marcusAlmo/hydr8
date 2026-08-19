import uuid
from typing import Any


class GenericFakeRepository:
    """In-memory dictionary store simulating repository pattern without database reliance."""

    def __init__(self):
        self._store: dict[Any, dict[str, Any]] = {}

    def add(self, entity_id: Any, data: dict[str, Any]) -> dict[str, Any]:
        data['id'] = entity_id
        self._store[entity_id] = data
        return data

    def get(self, entity_id: Any) -> dict[str, Any] | None:
        return self._store.get(entity_id)

    def filter(self, **kwargs) -> list[dict[str, Any]]:
        results = []
        for item in self._store.values():
            match = True
            for key, val in kwargs.items():
                if item.get(key) != val:
                    match = False
                    break
            if match:
                results.append(item)
        return results

    def all(self) -> list[dict[str, Any]]:
        return list(self._store.values())

    def update(self, entity_id: Any, **kwargs) -> dict[str, Any] | None:
        if entity_id in self._store:
            self._store[entity_id].update(kwargs)
            return self._store[entity_id]
        return None

    def delete(self, entity_id: Any) -> bool:
        if entity_id in self._store:
            del self._store[entity_id]
            return True
        return False


class FakeUserRepository(GenericFakeRepository):
    def create_user(self, username: str, email: str = '', password: str = '', role: Any = None, **kwargs) -> dict[str, Any]:
        user_id = kwargs.get('id', uuid.uuid4())
        data = {
            'id': user_id,
            'username': username,
            'email': email,
            'password': password,
            'role': role,
            'status': kwargs.get('status', 'ACTIVE'),
            'first_name': kwargs.get('first_name', ''),
            'last_name': kwargs.get('last_name', ''),
            'pin': kwargs.get('pin'),
            'deleted_at': kwargs.get('deleted_at'),
        }
        return self.add(user_id, data)

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        matches = self.filter(username=username)
        return matches[0] if matches else None


class FakeRoleRepository(GenericFakeRepository):
    def __init__(self):
        super().__init__()
        self._auto_id = 1

    def create_role(self, name: str, description: str = '', is_default: bool = False) -> dict[str, Any]:
        role_id = self._auto_id
        self._auto_id += 1
        data = {
            'name': name,
            'description': description,
            'is_default': is_default,
        }
        return self.add(role_id, data)


class FakePermissionRepository(GenericFakeRepository):
    def __init__(self):
        super().__init__()
        self._auto_id = 1

    def create_permission(self, role_id: int, action: str, can_read=False, can_write=False, can_update=False, can_delete=False) -> dict[str, Any]:
        perm_id = self._auto_id
        self._auto_id += 1
        data = {
            'role_id': role_id,
            'action': action,
            'can_read': can_read,
            'can_write': can_write,
            'can_update': can_update,
            'can_delete': can_delete,
        }
        return self.add(perm_id, data)


class FakeCustomerRepository(GenericFakeRepository):
    def __init__(self):
        super().__init__()
        self._auto_id = 1

    def create_customer(self, name: str, debt_balance: float = 0.0, **kwargs) -> dict[str, Any]:
        cust_id = kwargs.get('id', self._auto_id)
        if isinstance(cust_id, int) and cust_id >= self._auto_id:
            self._auto_id = cust_id + 1
        data = {
            'id': cust_id,
            'name': name,
            'debt_balance': debt_balance,
            'borrowed_round_8gal': kwargs.get('borrowed_round_8gal', 0),
            'borrowed_slim_8gal': kwargs.get('borrowed_slim_8gal', 0),
            'borrowed_other': kwargs.get('borrowed_other', 0),
        }
        return self.add(cust_id, data)


class FakeRemittanceRepository(GenericFakeRepository):
    def __init__(self):
        super().__init__()
        self._auto_id = 1

    def create_remittance(self, date_str: str, created_by_id: Any, status: str = 'DRAFT', **kwargs) -> dict[str, Any]:
        rem_id = kwargs.get('id', self._auto_id)
        if isinstance(rem_id, int) and rem_id >= self._auto_id:
            self._auto_id = rem_id + 1
        data = {
            'id': rem_id,
            'date': date_str,
            'created_by_id': created_by_id,
            'status': status,
            'total_sales': kwargs.get('total_sales', 0.0),
            'net_profit': kwargs.get('net_profit', 0.0),
        }
        return self.add(rem_id, data)


class FakeProductRepository(GenericFakeRepository):
    def __init__(self):
        super().__init__()
        self._auto_id = 1

    def create_product(self, name: str, variation: str, price: float, is_active: bool = True) -> dict[str, Any]:
        prod_id = self._auto_id
        self._auto_id += 1
        data = {
            'name': name,
            'variation': variation,
            'price': price,
            'is_active': is_active,
        }
        return self.add(prod_id, data)
