from sentinel.scoring import consistency_score

def test_consistency_identical_is_100():
    assert consistency_score(["yes you qualify", "yes you qualify"]) == 100

def test_consistency_disjoint_is_low():
    assert consistency_score(["yes you qualify", "absolutely not denied"]) < 40

def test_consistency_single_response_is_100():
    assert consistency_score(["anything"]) == 100
