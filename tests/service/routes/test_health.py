from httpx import AsyncClient


async def test_health_returns_ok_without_token(anonymous_client: AsyncClient) -> None:
    response = await anonymous_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
