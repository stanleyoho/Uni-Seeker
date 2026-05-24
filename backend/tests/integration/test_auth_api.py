import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_register_and_login_flow(client: AsyncClient, db_session: AsyncSession):
    # 1. Test Registration
    register_data = {
        "email": "test@example.com",
        "password": "Password123", # Must contain letter and number
        "username": "testuser"     # Required field
    }
    response = await client.post("/api/v1/auth/register", json=register_data)
    assert response.status_code == 201 # Defined as 201 in API
    data = response.json()
    assert "access_token" in data

    # Verify user exists in DB
    result = await db_session.execute(select(User).where(User.email == "test@example.com"))
    user = result.scalar_one_or_none()
    assert user is not None
    assert user.username == "testuser"

    # 2. Test Login
    login_data = {
        "email": "test@example.com",
        "password": "Password123"
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    token = data["access_token"]

    # 3. Test Get Me (Authenticated)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"

@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    login_data = {
        "email": "nonexistent@example.com",
        "password": "WrongPassword123"
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db_session: AsyncSession):
    # Seed a user - using a longer dummy hash
    user = User(email="duplicate@example.com", hashed_password="a" * 60, username="existing")
    db_session.add(user)
    await db_session.commit()

    register_data = {
        "email": "duplicate@example.com",
        "password": "Password123",
        "username": "newuser"
    }
    response = await client.post("/api/v1/auth/register", json=register_data)
    assert response.status_code == 400

    data = response.json()
    # The application uses a custom error handler that returns 'message'
    assert "message" in data
    assert "Email already registered" in data["message"]
