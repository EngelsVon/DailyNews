from app import app

with app.app_context():
    for r in app.url_map.iter_rules():
        if '/api/' in r.rule:
            print(r.rule, sorted(list(r.methods)))