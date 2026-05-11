from app import create_app
from flask import session

app = create_app()

@app.route('/test-render')
def test_render():
    from app.routes.student import attend_theory
    return attend_theory(18)

with app.test_request_context('/test-render'):
    session['user_id'] = 5
    session['user_type'] = 'student'
    session['school_id'] = 1
    # We might need to fake login_required or bypass it.
    # Actually, we can just call `attend_theory` directly.
    try:
        from app.routes.student import attend_theory
        resp = attend_theory(18)
        print(resp)
    except Exception as e:
        import traceback
        traceback.print_exc()
