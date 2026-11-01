from src.guards import GuardInput, permit_signal

def test_permit_when_all_clear():
    g=GuardInput(.8,True,True,.001,False,True,True)
    assert permit_signal(g)["allowed"]

def test_emergency_stop_blocks():
    g=GuardInput(.99,True,True,0,True,True,True)
    r=permit_signal(g)
    assert not r["allowed"] and "emergency_stop" in r["reasons"]

def test_news_blocks():
    g=GuardInput(.9,True,False,0,False,True,True)
    assert not permit_signal(g)["allowed"]
