from app.router import classify

def test_identifier_routes_to_hybrid():
    assert classify("What does DR-002 say?")[0] == "hybrid"

def test_snake_case_routes_to_hybrid():
    assert classify("explain max_upload_mb")[0] == "hybrid"

def test_short_term_routes_to_hybrid():
    assert classify("Celery")[0] == "hybrid"

def test_conceptual_question_routes_to_vector():
    assert classify("Why did the team adopt semantic retrieval?")[0] == "vector"

def test_every_route_has_a_reason():
    assert classify("How slow were the slowest requests?")[1]