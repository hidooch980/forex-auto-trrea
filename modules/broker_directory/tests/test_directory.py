import pytest

from modules.broker_directory.directory import list_servers, save_server, search_brokers


def test_catalog_search_finds_known_broker():
    results = search_brokers(101, "pepper")
    assert results
    assert results[0]["name"] == "Pepperstone"


def test_user_can_save_and_autocomplete_demo_and_live_servers(tmp_path, monkeypatch):
    from modules.broker_directory import directory
    monkeypatch.setattr(directory, "DB_PATH", tmp_path / "brokers.sqlite3")
    demo = save_server(7, "My Local Broker", "mt5", "demo", "MyBroker-Demo02")
    live = save_server(7, "My Local Broker", "mt5", "live", "MyBroker-Live01")
    assert demo["environment"] == "demo"
    assert live["environment"] == "live"
    assert [x["server_name"] for x in list_servers(7, "My Local Broker", "mt5", "demo")] == ["MyBroker-Demo02"]
    assert [x["server_name"] for x in list_servers(7, "My Local Broker", "mt5", "live")] == ["MyBroker-Live01"]
    assert any(x["name"] == "My Local Broker" for x in search_brokers(7, "local"))


def test_server_entries_are_isolated_by_user(tmp_path, monkeypatch):
    from modules.broker_directory import directory
    monkeypatch.setattr(directory, "DB_PATH", tmp_path / "brokers.sqlite3")
    save_server(1, "Broker", "mt5", "demo", "Broker-Demo")
    assert list_servers(2, "Broker") == []


@pytest.mark.parametrize("environment", ["paper", "", "DEMO"])
def test_invalid_environment_rejected(environment):
    with pytest.raises(ValueError):
        save_server(1, "Broker", "mt5", environment, "Broker-Demo")


def test_never_accepts_password_field_or_non_mt_platform():
    with pytest.raises(ValueError):
        save_server(1, "Broker", "ctrader", "demo", "Broker-Demo")
