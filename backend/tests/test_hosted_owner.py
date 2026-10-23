from sqlalchemy import func, select

from app.auth import hasher
from app.models import Membership, User
from scripts.bootstrap import create_owner


def test_hosted_owner_comes_from_a_hash_and_is_never_overwritten(session):
    password_hash = hasher.hash("synthetic owner password")
    user, created = create_owner(session, "Owner@Example.test", "Owner", password_hash=password_hash)
    assert created and user.email == "owner@example.test"
    assert hasher.verify(user.password_hash, "synthetic owner password")
    roles = session.scalars(select(Membership.role).where(Membership.user_id == user.id)).all()
    assert roles == ["owner", "owner", "owner"]
    # A later start with another hash leaves the account (and any changed password) alone.
    again, created = create_owner(
        session, "owner@example.test", "Owner", password_hash=hasher.hash("other one!!")
    )
    assert not created and again.id == user.id and again.password_hash == password_hash
    assert session.scalar(select(func.count()).select_from(User).where(User.email == user.email)) == 1


def test_hosted_owner_refuses_anything_but_an_argon2id_hash(session):
    import pytest

    with pytest.raises(ValueError):
        create_owner(session, "owner@example.test", "Owner", password_hash="plain password")
