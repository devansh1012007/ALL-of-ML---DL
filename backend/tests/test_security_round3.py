"""The security work of the third round (plan G, the items that were open).

They pin:

* key rotation (plan G1): a token carries the id of its key, a rotation
  accepts the old key for old tokens and signs with the new one, and a key
  that was never accepted verifies nothing;
* the ``role`` claim is gone from the token (plan G1): the role comes from
  the database, and the token must not carry a copy a client could trust;
* ``token_version`` revocation (plan A2/G): a bump ends the sessions that
  were issued before it;
* the security headers (plan G2) are on every response;
* a deployment that sends the refresh cookie refuses to start behind a
  wildcard CORS allow-list (plan A2/G2);
* a Hugging Face dataset reference is a hub identifier or nothing (plan G3);
* the zip of a graph dataset is checked before a byte of it is read
  (plan G3): zip-slip names, symlink members and decompression bombs are
  refused.
"""

import io
import os
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.app import graph_models, model_training
from backend.app.auth import (
    ALGORITHM,
    SECRET_KEY,
    create_token,
    decode_token,
    key_id,
)
from backend.app.main import app


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def registered_user(client):
    username = "sec3_user"
    client.post("/api/v1/register", json={"username": username, "password": "secret123"})
    token = client.post(
        "/token", data={"username": username, "password": "secret123"}
    ).json()["access_token"]
    return username, {"Authorization": f"Bearer {token}"}


# --- key rotation (plan G1) ---------------------------------------------------


def _fresh_process(environment, program):
    # The conftest has already pointed DATABASE_URL at the throwaway SQLite
    # database of the run, and that value is inherited here: the subprocess
    # imports the application, which builds its engine at import time.
    env = dict(os.environ, PYTHONPATH=REPO_ROOT)
    env.pop("SECRET_KEY", None)
    env.update(environment)
    return subprocess.run(
        [sys.executable, "-c", program],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )


def test_a_token_carries_the_id_of_its_key():
    token = create_token({"sub": "someone"})
    header = __import__("jose").jwt.get_unverified_header(token)
    assert header.get("kid") == key_id(SECRET_KEY)


def test_a_rotation_verifies_old_tokens_and_signs_with_the_new_key():
    """SECRET_KEYS = 'new,old': the old token still verifies, new tokens sign
    with the first key."""
    old_key, new_key = "the-old-key-value-0123456789", "the-new-key-value-9876543210"
    program = (
        "import backend.app.auth as auth, json\n"
        f"old = auth.create_token({{'sub': 'alice'}}, signing_key={old_key!r})\n"
        "new = auth.create_token({'sub': 'bob'})\n"
        "print(json.dumps({\n"
        "    'old_ok': auth.decode_token(old)['sub'] == 'alice',\n"
        "    'new_signer': __import__('jose').jwt.get_unverified_header(new)['kid'],\n"
        f"    'new_kid': auth.key_id({new_key!r}),\n"
        "}))\n"
    )
    result = _fresh_process(
        {"SECRET_KEYS": f"{new_key},{old_key}"},
        program,
    )
    assert result.returncode == 0, result.stderr
    payload = __import__("json").loads(result.stdout.strip().splitlines()[-1])
    assert payload["old_ok"] is True
    assert payload["new_signer"] == payload["new_kid"]


def test_a_key_that_was_never_accepted_verifies_nothing():
    program = (
        "import backend.app.auth as auth\n"
        "token = auth.create_token({'sub': 'alice'}, signing_key='attacker-key-000000')\n"
        "try:\n"
        "    auth.decode_token(token)\n"
        "    print('ACCEPTED')\n"
        "except Exception:\n"
        "    print('REFUSED')\n"
    )
    result = _fresh_process({"SECRET_KEYS": "real-key-1234567890"}, program)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "REFUSED"


def test_a_forged_kid_cannot_smuggle_a_foreign_key(client, registered_user):
    """A token whose ``kid`` names a key we do not hold is still only accepted
    when one of the accepted keys verifies it."""
    username, headers = registered_user
    forged = __import__("jose").jwt.encode(
        {"sub": username},
        "attacker-key-000000",
        algorithm=ALGORITHM,
        headers={"kid": key_id(SECRET_KEY)},
    )
    response = client.get(
        "/api/v1/ml/models", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401


def test_the_role_claim_is_gone_from_the_token(client, registered_user):
    username, headers = registered_user
    token = headers["Authorization"].removeprefix("Bearer ")
    payload = decode_token(token)
    assert "role" not in payload
    assert payload["sub"] == username


def test_admin_user_delete_increments_token_version(client, registered_user):
    """The token_version of the login is the version of the row: a bump by an
    admin action ends the sessions issued before it."""
    username, headers = registered_user
    ok = client.get("/api/v1/ml/models", headers=headers)
    assert ok.status_code == 200

    # The check is enforced in get_current_user; the suspension path of the
    # admin API is covered in test_admin.py. Here the enforcement itself:
    from backend.app.models import User
    import asyncio
    from backend.app.database import AsyncSessionLocal
    from sqlalchemy import select as _select

    async def _bump():
        async with AsyncSessionLocal() as session:
            result = await session.execute(_select(User).where(User.username == username))
            user = result.scalars().first()
            user.token_version = (user.token_version or 0) + 1
            await session.commit()

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_bump())

    stale = client.get("/api/v1/ml/models", headers=headers)
    assert stale.status_code == 401


# --- security headers (plan G2) ------------------------------------------------


def test_the_security_headers_are_on_every_response(client, registered_user):
    _, headers = registered_user
    response = client.get("/api/v1/ml/models", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("referrer-policy") == "no-referrer"
    csp = response.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in csp
    assert "default-src 'self'" in csp


def test_the_security_headers_are_on_an_error_too(client):
    response = client.get("/api/v1/ml/models")
    assert response.status_code == 401
    assert response.headers.get("x-content-type-options") == "nosniff"


def test_a_wildcard_cors_with_the_refresh_cookie_refuses_to_start():
    program = "import backend.app.main\nprint('STARTED')"
    result = _fresh_process(
        {"CORS_ORIGINS": "*", "REFRESH_COOKIE_ENABLED": "1"}, program
    )
    assert result.returncode != 0
    assert "CORS_ORIGINS" in result.stderr


def test_a_wildcard_cors_without_the_cookie_still_starts():
    program = "import backend.app.main\nprint('STARTED')"
    result = _fresh_process(
        {"CORS_ORIGINS": "*", "REFRESH_COOKIE_ENABLED": "0"}, program
    )
    assert result.returncode == 0, result.stderr
    assert "STARTED" in result.stdout


# --- Hugging Face references (plan G3) ------------------------------------------


@pytest.mark.parametrize(
    "reference",
    [
        "owner/name",
        "squad",
        "https://huggingface.co/datasets/owner/name",
        "https://www.huggingface.co/datasets/squad",
    ],
)
def test_a_hub_identifier_is_accepted(reference):
    assert model_training.validate_hf_dataset_reference(reference)


@pytest.mark.parametrize(
    "reference",
    [
        "https://evil.example.com/payload.json",
        "file:///etc/passwd",
        "/etc/passwd",
        "../../etc/passwd",
        "owner/name@refs/pr/1",
        "csv://path/to/file",
        "owner/../secret",
        "",
        "   ",
    ],
)
def test_an_arbitrary_url_or_path_is_refused(reference):
    with pytest.raises(ValueError):
        model_training.validate_hf_dataset_reference(reference)


def test_the_train_endpoint_refuses_a_foreign_url(client, registered_user):
    _, headers = registered_user
    response = client.post(
        "/api/v1/ml/train",
        json={
            "model_name": "Logistic_Regression",
            "hf_dataset_url": "https://evil.example.com/payload.json",
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "huggingface.co" in response.json()["detail"] or "identifier" in response.json()["detail"]


# --- the zip of a graph dataset (plan G3) ----------------------------------------


def _zip_with(*members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, content)
    return buffer.getvalue()


def _graph_zip():
    return _zip_with(
        ("nodes.csv", "node_id,label\na,0\nb,1\n"),
        ("edges.csv", "source,target\na,b\n"),
    )


def test_an_honest_graph_zip_is_accepted(tmp_path):
    path = tmp_path / "graph.zip"
    path.write_bytes(_graph_zip())
    nodes, edges = graph_models._load_graph(path)
    assert list(nodes["node_id"]) == ["a", "b"]
    assert len(edges) == 1


def test_a_member_that_climbs_out_is_refused(tmp_path):
    payload = _zip_with(
        ("nodes.csv", "node_id,label\na,0\n"),
        ("edges.csv", "source,target\na,b\n"),
        ("../escape.csv", "nope\n"),
    )
    path = tmp_path / "graph.zip"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="climbs out"):
        graph_models._safe_zip_members(path)


def test_an_absolute_member_path_is_refused(tmp_path):
    payload = _zip_with(
        ("nodes.csv", "node_id,label\na,0\n"),
        ("edges.csv", "source,target\na,b\n"),
        ("/etc/escape.csv", "nope\n"),
    )
    path = tmp_path / "graph.zip"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="absolute path"):
        graph_models._safe_zip_members(path)


def test_a_symlink_member_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        info = zipfile.ZipInfo("nodes.csv")
        info.external_attr = (0o120777 & 0xFFFF) << 16  # a symlink
        archive.writestr(info, "/etc/passwd")
        plain = zipfile.ZipInfo("edges.csv")
        plain.external_attr = (0o100644 & 0xFFFF) << 16
        archive.writestr(plain, "source,target\na,b\n")
    path = tmp_path / "graph.zip"
    path.write_bytes(buffer.getvalue())
    with pytest.raises(ValueError, match="symlink"):
        graph_models._safe_zip_members(path)


def test_an_archive_of_too_many_members_is_refused(tmp_path):
    members = [
        (f"file_{index}.txt", "x") for index in range(graph_models.MAX_ZIP_MEMBERS + 1)
    ]
    path = tmp_path / "graph.zip"
    path.write_bytes(_zip_with(*members))
    with pytest.raises(ValueError, match="limit"):
        graph_models._safe_zip_members(path)


def test_a_decompression_bomb_is_refused_before_it_is_read(tmp_path, monkeypatch):
    """A member whose declared unpacked size is over the cap is refused from
    the central directory: nothing is read into memory. The cap is shrunk for
    the test - the refusal reads the declared size, so the code path is the
    same one a real bomb would hit."""
    monkeypatch.setattr(graph_models, "MAX_ZIP_UNCOMPRESSED_BYTES", 8)
    path = tmp_path / "graph.zip"
    path.write_bytes(_graph_zip())
    with pytest.raises(ValueError, match="unpacks to more"):
        graph_models._safe_zip_members(path)


def test_a_corrupt_zip_is_refused_with_a_readable_reason(tmp_path):
    path = tmp_path / "graph.zip"
    path.write_bytes(b"this is not a zip file at all")
    with pytest.raises(ValueError, match="not a readable zip"):
        graph_models._safe_zip_members(path)
