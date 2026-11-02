import pytest

import account_registry as registry


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "DB_PATH", tmp_path / "accounts.sqlite3")


def payload(**changes):
    data = {
        "label": "My FTMO account",
        "account_number": "123456",
        "product": "cfd_2_step",
        "phase": "challenge",
        "account_type": "standard",
        "platform": "mt5",
        "initial_capital": 100000,
        "currency": "USD",
    }
    data.update(changes)
    return data


def test_add_and_list_accounts_are_scoped_to_user(isolated_db):
    first = registry.add_account(10, payload())
    registry.add_account(11, payload(account_number="654321", label="Other user"))
    assert first["product"] == "cfd_2_step"
    assert len(registry.list_accounts(10)) == 1
    assert len(registry.list_accounts(11)) == 1


def test_product_phase_and_account_type_are_validated(isolated_db):
    with pytest.raises(ValueError):
        registry.add_account(10, payload(product="cfd_1_step", phase="verification"))
    with pytest.raises(ValueError):
        registry.add_account(10, payload(product="futures", phase="evaluation", account_type="swing"))


def test_supports_all_configured_product_families(isolated_db):
    examples = [
        payload(product="cfd_1_step", phase="funded", account_type="swing"),
        payload(product="cfd_2_step", phase="verification", account_type="standard", account_number="2"),
        payload(product="cfd_instant", phase="instant", account_type="standard", account_number="3"),
        payload(product="futures", phase="sim_funded", account_type="growth", account_number="4"),
        payload(product="free_trial", phase="trial", account_type="swing", account_number="5"),
    ]
    for item in examples:
        registry.add_account(10, item)
    assert len(registry.list_accounts(10)) == 5


def test_duplicate_account_number_is_rejected(isolated_db):
    registry.add_account(10, payload())
    with pytest.raises(Exception):
        registry.add_account(10, payload(label="Duplicate"))
