import pytest
import httpx
from datetime import datetime, timedelta, timezone


BASE_URL = "http://localhost:8000"


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE_URL) as c:
        yield c


def future_time(hours=5):
    return (
        datetime.now(timezone.utc)
        + timedelta(hours=hours)
    ).isoformat()


def register(client, org, username):
    return client.post(
        "/auth/register",
        json={
            "org_name": org,
            "username": username,
            "password": "password123"
        }
    )


def login(client, org, username):
    return client.post(
        "/auth/login",
        json={
            "org_name": org,
            "username": username,
            "password": "password123"
        }
    )


def auth_header(token):
    return {
        "Authorization": f"Bearer {token}"
    }


# -----------------------------
# HEALTH
# -----------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# -----------------------------
# AUTH TESTS
# -----------------------------

def test_register_new_org_admin(client):

    r = register(
        client,
        "org_test_1",
        "admin1"
    )

    assert r.status_code == 200

    data = r.json()

    assert data["role"] == "admin"
    assert "id" in data
    assert "org_id" in data



def test_register_existing_org_member(client):

    register(
        client,
        "org_member",
        "owner"
    )

    r = register(
        client,
        "org_member",
        "member1"
    )

    assert r.status_code == 200

    assert r.json()["role"] == "member"



def test_duplicate_username(client):

    register(
        client,
        "duplicate_org",
        "sameuser"
    )

    r = register(
        client,
        "duplicate_org",
        "sameuser"
    )

    assert r.status_code == 409
    assert r.json()["code"] == "USERNAME TAKEN"



def test_invalid_login(client):

    r = client.post(
        "/auth/login",
        json={
            "org_name": "wrong",
            "username": "none",
            "password": "bad"
        }
    )

    assert r.status_code == 401



def test_login_success(client):

    register(
        client,
        "login_org",
        "login_user"
    )

    r = login(
        client,
        "login_org",
        "login_user"
    )

    assert r.status_code == 200

    data = r.json()

    assert "access_token" in data
    assert "refresh_token" in data



# -----------------------------
# ROOM TESTS
# -----------------------------


def create_admin(client):

    register(
        client,
        "room_org",
        "room_admin"
    )

    token = login(
        client,
        "room_org",
        "room_admin"
    ).json()["access_token"]

    return token



def test_create_room(client):

    token = create_admin(client)

    r = client.post(
        "/rooms",
        headers=auth_header(token),
        json={
            "name": "Conference",
            "capacity": 20,
            "hourly_rate_cents": 500
        }
    )

    assert r.status_code == 200



def test_member_cannot_create_room(client):

    register(
        client,
        "room_permission",
        "admin"
    )

    register(
        client,
        "room_permission",
        "member"
    )


    token = login(
        client,
        "room_permission",
        "member"
    ).json()["access_token"]


    r = client.post(
        "/rooms",
        headers=auth_header(token),
        json={
            "name": "X",
            "capacity": 5,
            "hourly_rate_cents": 100
        }
    )


    assert r.status_code == 403



# -----------------------------
# BOOKING VALIDATION
# -----------------------------


def setup_booking():

    client = httpx.Client(
        base_url=BASE_URL
    )

    register(
        client,
        "booking_org",
        "booker"
    )

    token = login(
        client,
        "booking_org",
        "booker"
    ).json()["access_token"]


    client.post(
        "/rooms",
        headers=auth_header(token),
        json={
            "name":"Room1",
            "capacity":10,
            "hourly_rate_cents":1000
        }
    )


    rooms = client.get(
        "/rooms",
        headers=auth_header(token)
    ).json()


    return client, token, rooms[0]["id"]



def test_booking_past_time(client):

    register(
        client,
        "past_org",
        "user1"
    )

    token = login(
        client,
        "past_org",
        "user1"
    ).json()["access_token"]


    r = client.post(
        "/bookings",
        headers=auth_header(token),
        json={
            "room_id":1,
            "start_time":
                "2020-01-01T00:00:00Z",
            "end_time":
                "2020-01-01T01:00:00Z"
        }
    )


    assert r.status_code == 400



def test_booking_duration_more_than_8_hours(client):

    register(
        client,
        "duration_org",
        "user"
    )

    token = login(
        client,
        "duration_org",
        "user"
    ).json()["access_token"]


    r = client.post(
        "/bookings",
        headers=auth_header(token),
        json={
            "room_id":1,
            "start_time":future_time(),
            "end_time":future_time(10)
        }
    )

    assert r.status_code == 400



# -----------------------------
# DOUBLE BOOKING
# -----------------------------


def test_double_booking(client):

    token = create_admin(client)


    room = client.post(
        "/rooms",
        headers=auth_header(token),
        json={
            "name":"Overlap",
            "capacity":10,
            "hourly_rate_cents":200
        }
    ).json()


    body={
        "room_id":room["id"],
        "start_time":future_time(),
        "end_time":future_time(2)
    }


    r1 = client.post(
        "/bookings",
        headers=auth_header(token),
        json=body
    )


    r2 = client.post(
        "/bookings",
        headers=auth_header(token),
        json=body
    )


    assert r1.status_code in [200,201]

    assert r2.status_code == 409



# -----------------------------
# PAGINATION
# -----------------------------


def test_booking_pagination(client):

    token=create_admin(client)

    r=client.get(
        "/bookings?page=1&limit=10",
        headers=auth_header(token)
    )


    assert r.status_code==200

    data=r.json()

    assert "items" in data
    assert "total" in data



# -----------------------------
# LOGOUT
# -----------------------------


def test_logout(client):

    token=create_admin(client)


    r=client.post(
        "/auth/logout",
        headers=auth_header(token)
    )

    assert r.status_code==200


    r2=client.get(
        "/rooms",
        headers=auth_header(token)
    )

    assert r2.status_code==401



# -----------------------------
# REFRESH TOKEN
# -----------------------------


def test_refresh_rotation(client):

    register(
        client,
        "refresh_org",
        "refresh_user"
    )


    data=login(
        client,
        "refresh_org",
        "refresh_user"
    ).json()


    r=client.post(
        "/auth/refresh",
        json={
            "refresh_token":
                data["refresh_token"]
        }
    )


    assert r.status_code==200



# -----------------------------
# INVALID TOKEN
# -----------------------------


def test_invalid_token(client):

    r=client.get(
        "/rooms",
        headers={
            "Authorization":
            "Bearer fake"
        }
    )


    assert r.status_code==401